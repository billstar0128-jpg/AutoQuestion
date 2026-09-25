"""Explicit isolated Windows source-install verification, no real API credentials."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

from release_audit import ROOT, audit


def main():
    if sys.platform != 'win32':
        print('Clean-room acceptance requires Windows.')
        return 1
    files, issues = audit()
    if issues:
        print('Candidate audit failed; clean-room copy not created.')
        for item in issues:
            print(f'{item.path}:{item.line}: {item.kind}; content redacted')
        return 1
    temporary = Path(tempfile.mkdtemp(prefix='autoquestion-rc-'))
    source = temporary / 'source'
    source.mkdir()
    for path in files:
        destination = source / path.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
    profile = temporary / 'profile'
    appdata, localdata = profile / 'AppData/Roaming', profile / 'AppData/Local'
    for path in (appdata, localdata, temporary / 'tmp'):
        path.mkdir(parents=True, exist_ok=True)
    # Do not copy application variables, secrets, proxy config or Python paths.
    system_names = {'SYSTEMROOT', 'WINDIR', 'PATH', 'COMSPEC', 'PATHEXT'}
    env = {key: value for key, value in os.environ.items() if key.upper() in system_names}
    env.update(APPDATA=str(appdata), LOCALAPPDATA=str(localdata), USERPROFILE=str(profile),
               TEMP=str(temporary / 'tmp'), TMP=str(temporary / 'tmp'),
               PYTHONUTF8='1', PYTHONIOENCODING='utf-8', PLAYWRIGHT_BROWSERS_PATH='0',
               PIP_CONFIG_FILE=os.devnull)
    python = source / '.venv-win/Scripts/python.exe'
    steps = [
        ('create-venv', [sys._base_executable, '-m', 'venv', '.venv-win']),
        ('runtime-install', [str(python), '-m', 'pip', '--isolated', 'install', '--no-cache-dir', '-r', 'requirements.txt']),
        ('chromium-install', [str(python), '-m', 'playwright', 'install', 'chromium']),
        ('version', [str(python), 'main.py', '--version']),
        ('doctor', [str(python), 'main.py', '--doctor']),
        ('show-config', [str(python), 'main.py', '--show-config']),
        ('dev-install', [str(python), '-m', 'pip', '--isolated', 'install', '-r', 'requirements-dev.txt']),
        ('metadata-install', [str(python), '-m', 'pip', '--isolated', 'install', '--no-deps', '-e', '.']),
        ('metadata-version', [str(python), '-c',
            "from importlib.metadata import version; from autoquestion import __version__; "
            "assert version('autoquestion') == __version__; print('Metadata version:', __version__)"]),
        # Setup tests inject temp config and fake vault; entrypoint tests use explicit fake/demo.
        ('pytest', [str(python), '-m', 'pytest', '-q']),
        ('unittest', [str(python), '-m', 'unittest', 'discover', '-s', 'tests', '-v']),
        ('compileall', [str(python), '-m', 'compileall', '-q', 'main.py', 'src', 'tests', 'tools']),
        ('pip-check', [str(python), '-m', 'pip', 'check']),
        ('candidate-audit', [str(python), 'tools/release_audit.py']),
        ('installed-versions', [str(python), '-m', 'pip', 'list', '--format=json']),
    ]
    print(f'Clean-room directory: {temporary}', flush=True)
    results = []
    for name, command in steps:
        print(f'Running {name}...', flush=True)
        started = time.monotonic()
        log = temporary / f'{name}.log'
        try:
            with log.open('w', encoding='utf-8') as output:
                completed = subprocess.run(command, cwd=source, env=env, stdout=output,
                                           stderr=subprocess.STDOUT, timeout=1200)
            code = completed.returncode
        except (OSError, subprocess.TimeoutExpired):
            code = -1
        results.append({'step': name, 'exit_code': code, 'seconds': round(time.monotonic()-started, 2)})
        (temporary / 'results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
        print(f'{name}: {"PASS" if code == 0 else "FAIL"}; exit={code}; log={log}', flush=True)
        if code:
            print('Stopped at failed step; isolated directory retained for review.')
            return 1
    # The shared isolated profile must remain free of actual application config.
    if (appdata / 'AutoQuestion/config.json').exists():
        print('FAIL: unexpected application configuration in clean-room shared profile.')
        return 1
    print('Clean-room PASS. Source-copy install, not a git clone. No public publication.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
