"""Build only audited project assets and installed third-party dependencies."""
from importlib import metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from autoquestion import __version__
from release_audit import audit


def main():
    if sys.platform != 'win32':
        raise SystemExit('Windows x64 build required.')
    _, findings = audit(ROOT)
    assert not findings, 'Source audit failed; bundle not built'
    output = ROOT / 'dist/windows'
    build = ROOT / 'build/windows'
    output.mkdir(parents=True, exist_ok=True)
    build.mkdir(parents=True, exist_ok=True)
    assert output.resolve().is_relative_to(ROOT.resolve()) and build.resolve().is_relative_to(ROOT.resolve())
    assert (output / 'AutoQuestion').resolve().is_relative_to(output.resolve())
    import tkinter
    tcl_version = tkinter.Tcl().eval('info patchlevel')
    tcl_license = build / ('tcl-' + tcl_version + '-license.terms.txt')
    if not tcl_license.is_file():
        tag = 'core-' + tcl_version.replace('.', '-')
        with urllib.request.urlopen('https://raw.githubusercontent.com/tcltk/tcl/' + tag + '/license.terms', timeout=30) as response:
            tcl_license.write_bytes(response.read())
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onedir', '--windowed',
               '--noupx', '--disable-windowed-traceback', '--name', 'AutoQuestion', '--icon', 'NONE',
               '--paths', str(ROOT / 'src'), '--distpath', str(output), '--workpath', str(build / 'work'),
               '--specpath', str(build), '--hidden-import', 'mss.windows',
               '--collect-submodules', 'autoquestion', '--collect-submodules', 'openai',
               '--collect-data', 'playwright', '--copy-metadata', 'pydantic']
    for source, target in (('src/autoquestion/web', 'autoquestion/web'),
                           ('src/autoquestion/capture/dom_extract.js', 'autoquestion/capture'),
                           ('extension', 'extension'), ('examples', 'examples'), ('LICENSE', '.')):
        command += ['--add-data', str(ROOT / source) + ':' + target]
    # This build venv has no installed Chromium/profile cache. Do not use --collect-all
    # on a user's Playwright installation; that could bundle private/runtime data.
    import playwright
    assert not (Path(playwright.__file__).parent / 'driver/package/.local-browsers').exists()
    subprocess.run(command + [str(ROOT / 'tools/desktop_entry.py')], cwd=ROOT, check=True)
    app = output / 'AutoQuestion'
    shutil.copyfile(ROOT / 'LICENSE', app / 'LICENSE.txt')
    shutil.copytree(ROOT / 'extension', app / 'extension', dirs_exist_ok=True)
    licenses = app / 'THIRD_PARTY_LICENSES'
    licenses.mkdir(exist_ok=True)
    shutil.copyfile(tcl_license, licenses / tcl_license.name)
    installed = []
    for distribution in metadata.distributions():
        name, version = distribution.metadata['Name'], distribution.version
        installed.append({'name': name, 'version': version})
        for entry in distribution.files or ():
            if entry.name.lower().startswith(('license', 'licence', 'copying', 'notice', 'authors')):
                path = Path(distribution.locate_file(entry))
                if path.is_file():
                    destination = licenses / name / entry.name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(path, destination)
    for path in (Path(sys.base_prefix) / 'LICENSE.txt', Path(sys.base_prefix) / 'tcl/tcl8.6/license.terms',
                 Path(sys.base_prefix) / 'tcl/tk8.6/license.terms'):
        if path.is_file():
            name = 'PYTHON-LICENSE.txt' if path.name == 'LICENSE.txt' else path.parent.name + '-license.terms.txt'
            shutil.copyfile(path, licenses / name)
    (licenses / 'PACKAGES.json').write_text(json.dumps(sorted(installed, key=lambda p:p['name']), indent=2), encoding='utf-8')
    (app / '开始使用.txt').write_text('AutoQuestion ' + __version__ + '\n\n1. 完整解压 ZIP，保留 _internal 文件夹。\n2. 双击 AutoQuestion.exe。无需安装 Python 或运行 PowerShell。\n3. 在本机工作台配置 URL、模型与自己的 API Key，保存后启动答题。\n4. 题目窗口置前台，按 F8；ESC 停止服务。\n\nChrome / Edge DOM 扩展在 extension 文件夹。\n普通 Vision 与 Offline Demo 无需安装 Chromium。\n这是未签名的开源便携版，不要求管理员权限。\n', encoding='utf-8')
    print('Portable app built:', app)


if __name__ == '__main__':
    main()
