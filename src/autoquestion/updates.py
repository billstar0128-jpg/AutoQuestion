"""Opt-in installation of hash-verified releases from this project's fixed GitHub source."""
from dataclasses import dataclass
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import uuid
import zipfile

from . import __version__

REPOSITORY = 'billstar0128-jpg/AutoQuestion'
RELEASES = f'https://api.github.com/repos/{REPOSITORY}/releases?per_page=100'
PAGE = f'https://github.com/{REPOSITORY}/releases'
INTERVAL = 15 * 60
MAX_ARCHIVE = 300 * 1024 * 1024
MAX_UNPACKED = 1536 * 1024 * 1024
VERSION = re.compile(r'(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})(?:-?(alpha|beta|rc)[.-]?(0|[1-9][0-9]{0,5}))?\Z')
CDN_HOSTS = {'release-assets.githubusercontent.com', 'objects.githubusercontent.com',
             'github-releases.githubusercontent.com'}


class UpdateError(ValueError):
    pass


def version_key(value):
    match = VERSION.fullmatch(value) if isinstance(value, str) else None
    if not match:
        raise UpdateError('不支持的版本格式。')
    major, minor, patch, stage, number = match.groups()
    return int(major), int(minor), int(patch), {None: 3, 'alpha': 0, 'beta': 1, 'rc': 2}[stage], int(number or 0)


@dataclass(frozen=True)
class Release:
    version: str
    url: str
    size: int
    digest: str
    checksums: 'Release | None' = None


def select_release(data, current=__version__):
    if not isinstance(data, list) or len(data) > 100:
        raise UpdateError('版本服务返回格式无效。')
    choices = []
    for item in data:
        if not isinstance(item, dict) or item.get('draft') is not False or not item.get('published_at'):
            continue
        tag = item.get('tag_name', '')
        if not isinstance(tag, str) or not tag.startswith('v'):
            continue
        version = tag[1:]
        try:
            if version_key(version) <= version_key(current):
                continue
        except UpdateError:
            continue
        name = f'AutoQuestion-{version}-Windows-x64.zip'
        expected_url = f'https://github.com/{REPOSITORY}/releases/download/{tag}/{name}'
        assets = item.get('assets')
        if not isinstance(assets, list):
            continue
        matches = [a for a in assets if isinstance(a, dict) and a.get('name') == name]
        if len(matches) != 1:
            continue
        asset = matches[0]
        digest, size = asset.get('digest'), asset.get('size')
        if (asset.get('state') != 'uploaded' or asset.get('browser_download_url') != expected_url
                or type(size) is not int or not 0 < size <= MAX_ARCHIVE
                or not isinstance(digest, str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', digest)):
            continue
        checksums = [a for a in assets if isinstance(a, dict) and a.get('name') == 'SHA256SUMS.txt']
        sums = None
        if checksums:
            if len(checksums) != 1:
                continue
            entry = checksums[0]
            sums_url = f'https://github.com/{REPOSITORY}/releases/download/{tag}/SHA256SUMS.txt'
            sums_digest, sums_size = entry.get('digest'), entry.get('size')
            if (entry.get('state') != 'uploaded' or entry.get('browser_download_url') != sums_url
                    or type(sums_size) is not int or not 0 < sums_size <= 65536
                    or not isinstance(sums_digest, str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', sums_digest)):
                continue
            sums = Release(version, sums_url, sums_size, sums_digest[7:])
        choices.append(Release(version, expected_url, size, digest[7:], sums))
    return max(choices, key=lambda release: version_key(release.version), default=None)


def allowed_url(url):
    try:
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443) or parsed.fragment:
            return False
        if parsed.hostname == 'api.github.com':
            return url == RELEASES
        if parsed.hostname == 'github.com':
            return parsed.path.startswith(f'/{REPOSITORY}/releases/download/') and not parsed.query
        return parsed.hostname in CDN_HOSTS and bool(parsed.path)
    except (ValueError, TypeError):
        return False


class _Redirects(HTTPRedirectHandler):
    max_redirections = 5
    max_repeats = 2
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not allowed_url(newurl):
            raise UpdateError('更新下载的跳转地址不受支持。')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class ReleaseClient:
    def __init__(self):
        self.opener = build_opener(_Redirects())

    def open(self, url):
        if not allowed_url(url):
            raise UpdateError('更新地址无效。')
        request = Request(url, headers={'User-Agent': 'AutoQuestion-Update/' + __version__,
                                       'Accept': 'application/vnd.github+json' if url == RELEASES else 'application/octet-stream',
                                       'Cache-Control': 'no-cache', 'X-GitHub-Api-Version': '2022-11-28'})
        response = self.opener.open(request, timeout=10)
        if not allowed_url(response.url):
            response.close()
            raise UpdateError('更新地址无效。')
        return response

    def latest(self, current):
        with self.open(RELEASES) as response:
            payload = response.read(4 * 1024 * 1024 + 1)
        if len(payload) > 4 * 1024 * 1024:
            raise UpdateError('版本信息过大。')
        return select_release(json.loads(payload), current)

    def download(self, release, destination, cancel, progress):
        if release.checksums:
            sums = release.checksums
            with self.open(sums.url) as response:
                payload = response.read(65537)
            if (cancel.is_set() or len(payload) != sums.size
                    or hashlib.sha256(payload).hexdigest() != sums.digest):
                raise UpdateError('更新校验文件不符。')
            name = release.url.rsplit('/', 1)[1]
            matches = [line for line in payload.decode('ascii').splitlines()
                       if re.fullmatch(r'[0-9a-f]{64}  ' + re.escape(name), line)]
            if matches != [release.digest + '  ' + name]:
                raise UpdateError('更新文件的两份校验信息不一致。')
        digest, received, deadline = hashlib.sha256(), 0, time.monotonic() + 20 * 60
        try:
            with self.open(release.url) as response, destination.open('xb') as output:
                while True:
                    if cancel.is_set() or time.monotonic() > deadline:
                        raise UpdateError('更新下载已取消或超时。')
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    received += len(chunk)
                    if received > release.size or received > MAX_ARCHIVE:
                        raise UpdateError('更新包大小不符。')
                    digest.update(chunk)
                    output.write(chunk)
                    progress(received * 100 // release.size)
            if received != release.size or digest.hexdigest() != release.digest:
                raise UpdateError('更新包校验失败，未安装。')
        except BaseException:
            destination.unlink(missing_ok=True)
            raise


def unpack_verified(archive, destination, cancel):
    """No extractall: reject traversal, aliases, links and oversized packages before writing."""
    with zipfile.ZipFile(archive) as package:
        members, seen, total = package.infolist(), set(), 0
        if not members or len(members) > 20000:
            raise UpdateError('更新包文件数量无效。')
        for item in members:
            raw = item.orig_filename
            path = PurePosixPath(raw)
            parts = path.parts
            if (not parts or parts[0] != 'AutoQuestion' or '\\' in raw or raw.rstrip('/') != path.as_posix()
                    or any(p in {'.', '..'} or p.endswith((' ', '.')) or re.search(r'[<>:"|?*\x00-\x1f]', p)
                           or p.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', 'CONIN$', 'CONOUT$',
                               *[f'COM{i}' for i in (*range(1, 10), '¹', '²', '³')],
                               *[f'LPT{i}' for i in (*range(1, 10), '¹', '²', '³')]}
                           for p in parts) or path.is_absolute()
                    or stat.S_ISLNK(item.external_attr >> 16)):
                raise UpdateError('更新包包含不安全的文件路径。')
            key = str(path).casefold()
            if key in seen:
                raise UpdateError('更新包包含重复文件路径。')
            seen.add(key)
            total += item.file_size
            if total > MAX_UNPACKED or item.file_size > 256 * 1024 * 1024:
                raise UpdateError('更新包解压大小超出限制。')
        for item in members:
            if cancel.is_set():
                raise UpdateError('更新已取消。')
            relative = PurePosixPath(item.filename).parts[1:]
            if not relative:
                continue
            target = destination.joinpath(*relative)
            if not target.resolve().is_relative_to(destination.resolve()):
                raise UpdateError('更新包路径无效。')
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with package.open(item) as source, target.open('xb') as output:
                    shutil.copyfileobj(source, output, 256 * 1024)
        if not (destination / 'AutoQuestion.exe').is_file() or not (destination / '_internal').is_dir():
            raise UpdateError('更新包缺少完整 App 文件。')


def app_root():
    root = Path(os.environ.get('LOCALAPPDATA', ''))
    if not root.is_absolute():
        raise UpdateError('无法定位本机更新目录。')
    return root / 'AutoQuestionApp'


class UpdateManager:
    def __init__(self, *, client=None, current=__version__, root=None, install_supported=None):
        self.client = ReleaseClient() if client is None else client
        self.current = current
        self.root = app_root() if root is None else Path(root)
        self.install_supported = (sys.platform == 'win32' and getattr(sys, 'frozen', False)
                                  if install_supported is None else install_supported)
        self.lock, self.cancel = threading.RLock(), threading.Event()
        self.release, self.target, self.worker = None, None, None
        self.status, self.message, self.progress, self.last_check = 'idle', '启动时及窗口打开期间每 15 分钟自动检查。', 0, 0

    def snapshot(self):
        with self.lock:
            return dict(status=self.status, message=self.message, progress=self.progress,
                        current=self.current, available=self.release.version if self.release else None,
                        install_supported=self.install_supported)

    def _work(self, action):
        def run():
            try:
                action()
            except Exception:
                with self.lock:
                    if not self.cancel.is_set():
                        self.status, self.message = 'error', '更新未完成。请检查 GitHub 网络连接后重试；答题功能仍可使用。'
        self.worker = threading.Thread(target=run, name='autoquestion-update', daemon=True)
        self.worker.start()

    def check(self):
        with self.lock:
            if self.cancel.is_set() or self.status in {'checking', 'downloading', 'installing'}:
                return self.snapshot()
            if self.last_check and time.monotonic() - self.last_check < 60:
                return self.snapshot()
            self.last_check = time.monotonic()
            self.status, self.message = 'checking', '正在检查 GitHub 版本…'
            def check():
                release = self.client.latest(self.current)
                with self.lock:
                    if self.cancel.is_set():
                        return
                    still_ready = release is not None and release == self.release and self.target is not None
                    self.release = release
                    if still_ready:
                        self.status, self.message = 'ready', '已下载最新可用版本，先停止答题再安装并重启。'
                    else:
                        self.target = None
                        self.status = 'available' if release else 'current'
                        self.message = f'发现 {release.version}，可下载更新。' if release else '未发现适用于本机的更高可校验发布版本。'
            self._work(check)
            return self.snapshot()

    def download(self):
        with self.lock:
            if not self.install_supported:
                raise UpdateError('源码运行请下载新版 Windows App。')
            if not self.release or self.status not in {'available', 'error'} or self.cancel.is_set():
                raise UpdateError('请先检查新版本，或等待当前更新完成。')
            release = self.release
            self.status, self.message, self.progress = 'downloading', '正在下载并校验更新包…', 0
            def download():
                self.root.mkdir(parents=True, exist_ok=True)
                with tempfile.TemporaryDirectory(prefix='.update-', dir=self.root) as temporary:
                    temporary = Path(temporary)
                    archive, extracted = temporary / 'download.zip', temporary / 'app'
                    extracted.mkdir()
                    def progress(percent):
                        with self.lock:
                            self.progress = percent
                    self.client.download(release, archive, self.cancel, progress)
                    unpack_verified(archive, extracted, self.cancel)
                    target = self.root / (release.version + '-' + uuid.uuid4().hex[:12])
                    with self.lock:
                        if self.cancel.is_set():
                            return
                        extracted.rename(target)
                        self.target = target
                        self.status, self.message = 'ready', '校验通过。先停止答题，再点击“安装并重启”。原配置保留。'
            self._work(download)
            return self.snapshot()

    def launch_installer(self):
        with self.lock:
            if self.status != 'ready' or self.target is None or not self.install_supported or self.cancel.is_set():
                raise UpdateError('尚无已校验的更新包。')
            receipt = self.root / ('apply-' + uuid.uuid4().hex + '.json')
            receipt.write_text(json.dumps(dict(version=self.release.version, target=str(self.target),
                                                parent=os.getpid())), encoding='utf-8')
            subprocess.Popen([sys.executable, '--apply-update', str(receipt)], close_fds=True,
                             creationflags=subprocess.CREATE_NO_WINDOW)
            self.status, self.message = 'installing', '正在退出旧版并启动新版…'

    def close(self):
        self.cancel.set()


def _wait_parent(pid):
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x100000, False, pid)
    if not handle:
        if ctypes.get_last_error() == 87:  # Parent already exited.
            return
        raise UpdateError('无法等待旧版本退出。')
    try:
        if kernel.WaitForSingleObject(handle, 120000) != 0:
            raise UpdateError('旧版本尚未退出，未替换快捷方式。')
    finally:
        kernel.CloseHandle(handle)


def _shortcut(executable):
    # Fixed script with correctly quoted literal path; no shell interpolation.
    quote = lambda value: "'" + str(value).replace("'", "''") + "'"
    script = ("$ErrorActionPreference='Stop'; $shell=New-Object -ComObject WScript.Shell; "
              "$file=Join-Path ([Environment]::GetFolderPath('Desktop')) 'AutoQuestion.lnk'; "
              "$link=$shell.CreateShortcut($file); $link.TargetPath=" + quote(executable) + '; '
              '$link.WorkingDirectory=' + quote(executable.parent) + "; $link.Arguments=''; "
              '$link.IconLocation=' + quote(str(executable) + ',0') + '; $link.Save()')
    encoded = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
    subprocess.run([str(Path(os.environ['SYSTEMROOT']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'),
                    '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
                   check=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def notify_ready(receipt):
    """Only the newly opened native window acknowledges an update inside our own install root."""
    try:
        root = app_root().resolve()
        receipt = Path(receipt).resolve()
        if receipt.parent != root or not re.fullmatch(r'apply-[0-9a-f]{32}\.json', receipt.name) or receipt.stat().st_size > 4096:
            return
        data = json.loads(receipt.read_text(encoding='utf-8'))
        if data['version'] != __version__ or Path(data['target']).resolve() != Path(sys.executable).resolve().parent:
            return
        receipt.with_suffix('.ready').write_text(json.dumps(dict(version=__version__, pid=os.getpid())), encoding='utf-8')
    except (OSError, ValueError, KeyError, TypeError):
        pass


def _wait_ready(receipt, process, version):
    ready = receipt.with_suffix('.ready')
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise UpdateError('新版未能启动，原桌面入口保留。')
        try:
            if ready.is_file() and ready.stat().st_size <= 1024:
                data = json.loads(ready.read_text(encoding='utf-8'))
                if data == dict(version=version, pid=process.pid):
                    return
        except (OSError, ValueError):
            pass
        time.sleep(0.1)
    raise UpdateError('新版窗口尚未就绪，原桌面入口保留。')


def apply_update(receipt, *, root=None, wait_parent=_wait_parent, shortcut=_shortcut, launcher=subprocess.Popen, wait_ready=_wait_ready):
    """Separate old EXE process waits for orderly exit; never overwrites/deletes a running install."""
    root = app_root().resolve() if root is None else Path(root).resolve()
    receipt = Path(receipt).resolve()
    if receipt.parent != root or not re.fullmatch(r'apply-[0-9a-f]{32}\.json', receipt.name) or receipt.stat().st_size > 4096:
        raise UpdateError('更新凭据路径无效。')
    data = json.loads(receipt.read_text(encoding='utf-8'))
    version = data['version']
    target = Path(data['target']).resolve()
    pid = data['parent']
    if (version_key(version) <= version_key(__version__) or target.parent != root
            or not re.fullmatch(re.escape(version) + r'-[0-9a-f]{12}', target.name)
            or type(pid) is not int or pid <= 0 or pid == os.getpid()
            or not (target / 'AutoQuestion.exe').is_file() or not (target / '_internal').is_dir()):
        raise UpdateError('更新凭据无效。')
    wait_parent(pid)
    executable = target / 'AutoQuestion.exe'
    # A failed process launch must leave the old desktop shortcut usable.
    process = launcher([str(executable), '--updated-app', str(receipt)], cwd=target, close_fds=True)
    wait_ready(receipt, process, version)
    shortcut(executable)
    receipt.with_suffix('.ready').unlink(missing_ok=True)
    receipt.unlink()
    return 0
