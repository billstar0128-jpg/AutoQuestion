param(
    [string]$JavaHome = $env:JAVA_HOME,
    [string]$SdkRoot = $env:ANDROID_HOME,
    [switch]$Release,
    [switch]$SkipChecks
)

# No Android SDK, API key, signing key, or local settings are bundled into the APK.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$toolchain = Join-Path $projectRoot 'build\android-toolchain'
$gradleVersion = '8.13'
$gradleSha256 = '20f1b1176237254a6fc204d8434196fa11a4cfb387567519c61556e8710aed78'
$gradleRoot = Join-Path $toolchain "gradle-$gradleVersion"
$gradleExe = Join-Path $gradleRoot 'bin\gradle.bat'

if (-not $JavaHome) {
    $localJdks = @(Get-ChildItem -Path (Join-Path $toolchain 'jdk*\*') -Directory -ErrorAction SilentlyContinue |
        Where-Object { Test-Path (Join-Path $_.FullName 'bin\javac.exe') })
    if ($localJdks.Count) { $JavaHome = $localJdks[-1].FullName }
}
if (-not $SdkRoot) { $SdkRoot = $env:ANDROID_SDK_ROOT }
if (-not $SdkRoot -and (Test-Path (Join-Path $toolchain 'sdk'))) { $SdkRoot = Join-Path $toolchain 'sdk' }
if (-not $JavaHome -or -not (Test-Path (Join-Path $JavaHome 'bin\javac.exe'))) {
    throw 'Install JDK 17 and set JAVA_HOME, or pass -JavaHome.'
}
if (-not $SdkRoot -or -not (Test-Path (Join-Path $SdkRoot 'platforms\android-36\android.jar'))) {
    throw 'Install Android SDK platform 36 and build-tools 35.0.0, then set ANDROID_HOME or pass -SdkRoot.'
}

if (-not (Test-Path $gradleExe)) {
    New-Item -ItemType Directory -Path $toolchain -Force | Out-Null
    $archive = Join-Path $toolchain "gradle-$gradleVersion-bin.zip"
    if (-not (Test-Path $archive) -or (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $gradleSha256) {
        & curl.exe --fail --location --retry 2 --connect-timeout 20 --max-time 900 --silent --show-error `
            --output $archive "https://services.gradle.org/distributions/gradle-$gradleVersion-bin.zip"
        if ($LASTEXITCODE -ne 0) { throw 'Gradle download failed. Retry or install the verified Gradle 8.13 distribution under build/android-toolchain.' }
    }
    if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $gradleSha256) {
        throw 'Gradle SHA-256 mismatch; refusing to execute the downloaded archive.'
    }
    Expand-Archive -LiteralPath $archive -DestinationPath $toolchain -Force
}

$managedVariables = @('JAVA_HOME', 'ANDROID_HOME', 'ANDROID_SDK_ROOT', 'GRADLE_USER_HOME',
    'ANDROID_KEYSTORE_FILE', 'ANDROID_KEYSTORE_PASSWORD', 'ANDROID_KEY_ALIAS', 'ANDROID_KEY_PASSWORD')
$previousEnvironment = @{}
foreach ($name in $managedVariables) { $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }

try {
    $env:JAVA_HOME = (Resolve-Path -LiteralPath $JavaHome).Path
    $env:ANDROID_HOME = (Resolve-Path -LiteralPath $SdkRoot).Path
    $env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
    $env:GRADLE_USER_HOME = Join-Path $projectRoot 'build\android-gradle-cache'

    if ($Release -and -not $env:ANDROID_KEYSTORE_FILE) {
        # Stable across clean builds. This folder is outside the checkout and must be backed up privately.
        $signingDir = Join-Path $env:LOCALAPPDATA 'AutoQuestionAndroidSigning'
        $keyFile = Join-Path $signingDir 'autoquestion-release.p12'
        $passwordFile = Join-Path $signingDir 'password.dpapi'
        New-Item -ItemType Directory -Path $signingDir -Force | Out-Null
        if ((Test-Path $keyFile) -ne (Test-Path $passwordFile)) {
            throw 'Incomplete Android signing backup. Restore both autoquestion-release.p12 and password.dpapi; do not replace the published signing key.'
        }
        if (-not (Test-Path $passwordFile)) {
            $passwordBytes = New-Object byte[] 32
            $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
            try { $generator.GetBytes($passwordBytes) } finally { $generator.Dispose() }
            $password = [Convert]::ToBase64String($passwordBytes)
            [Array]::Clear($passwordBytes, 0, $passwordBytes.Length)
            $securePassword = ConvertTo-SecureString -String $password -AsPlainText -Force
            ConvertFrom-SecureString -SecureString $securePassword | Set-Content -LiteralPath $passwordFile -Encoding ASCII
        } else {
            $securePassword = Get-Content -LiteralPath $passwordFile | ConvertTo-SecureString
            $password = [System.Net.NetworkCredential]::new('', $securePassword).Password
        }
        $env:ANDROID_KEYSTORE_FILE = $keyFile
        $env:ANDROID_KEYSTORE_PASSWORD = $password
        $env:ANDROID_KEY_ALIAS = 'autoquestion'
        $env:ANDROID_KEY_PASSWORD = $password
        if (-not (Test-Path $keyFile)) {
            & (Join-Path $env:JAVA_HOME 'bin\keytool.exe') -genkeypair -noprompt -keystore $keyFile -storetype PKCS12 `
                -alias autoquestion -keyalg RSA -keysize 3072 -validity 10000 `
                -dname 'CN=AutoQuestion Android, O=AutoQuestion' `
                -storepass:env ANDROID_KEYSTORE_PASSWORD -keypass:env ANDROID_KEY_PASSWORD
            if ($LASTEXITCODE -ne 0) { throw 'Could not generate the private Android signing key.' }
        }
        $password = $null
    }
    if ($Release) {
        foreach ($name in @('ANDROID_KEYSTORE_FILE', 'ANDROID_KEYSTORE_PASSWORD', 'ANDROID_KEY_ALIAS', 'ANDROID_KEY_PASSWORD')) {
            if (-not [Environment]::GetEnvironmentVariable($name, 'Process')) { throw "Missing release signing setting: $name" }
        }
    }

    $tasks = @('assembleDebug')
    if (-not $SkipChecks) { $tasks += @('testDebugUnitTest', 'lintDebug') }
    if ($Release) { $tasks += 'assembleRelease' }
    & $gradleExe -p (Join-Path $projectRoot 'android') --no-daemon --console=plain @tasks
    if ($LASTEXITCODE -ne 0) { throw 'Android build or validation failed.' }

    $variant = if ($Release) { 'release' } else { 'debug' }
    $apkDir = Join-Path $projectRoot "android\app\build\outputs\apk\$variant"
    $metadata = Get-Content -LiteralPath (Join-Path $apkDir 'output-metadata.json') -Raw | ConvertFrom-Json
    $element = $metadata.elements | Select-Object -First 1
    $apk = Join-Path $apkDir $element.outputFile
    $destination = Join-Path $projectRoot 'dist'
    New-Item -ItemType Directory -Path $destination -Force | Out-Null
    $suffix = if ($Release) { '' } else { '-debug' }
    $outputName = "AutoQuestion-$($element.versionName)-Android$suffix.apk"
    $output = Join-Path $destination $outputName
    Copy-Item -LiteralPath $apk -Destination $output -Force
    $sha = (Get-FileHash -LiteralPath $output -Algorithm SHA256).Hash.ToLowerInvariant()
    "$sha  $outputName" | Set-Content -LiteralPath (Join-Path $destination "$outputName.sha256") -Encoding ASCII
    & (Join-Path $env:ANDROID_HOME 'build-tools\35.0.0\apksigner.bat') verify --verbose --print-certs $output
    if ($LASTEXITCODE -ne 0) { throw 'APK signature verification failed.' }
    Write-Output "APK: $output"
    Write-Output "SHA-256: $sha"
    if ($Release -and $signingDir) { Write-Output "Private signing backup (never publish): $signingDir" }
} finally {
    foreach ($name in $managedVariables) { [Environment]::SetEnvironmentVariable($name, $previousEnvironment[$name], 'Process') }
    $password = $null
    if ($securePassword) { $securePassword.Dispose() }
}
