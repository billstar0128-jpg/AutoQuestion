"""Release protocol, network boundaries and installation using synthetic archives only."""
import base64
import hashlib
import io
import json
from pathlib import Path
import stat
import sys
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import Mock, patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from autoquestion import __version__
from autoquestion.updates import (MAX_ARCHIVE, PAGE, RELEASES, REPOSITORY, Release, ReleaseClient,
                                  UpdateError, UpdateManager, _Redirects, _shortcut,
                                  allowed_url, apply_update, select_release, unpack_verified, version_key)
from autoquestion.user_config import UserConfigStore
from autoquestion.web_ui import UIController, UIError
from test_core import wait_until


def entry(version='0.6.0', **changes):
    name = f'AutoQuestion-{version}-Windows-x64.zip'
    asset = dict(name=name, state='uploaded', size=10, digest='sha256:' + 'a' * 64,
                 browser_download_url=f'https://github.com/{REPOSITORY}/releases/download/v{version}/{name}')
    return dict(tag_name='v' + version, draft=False, published_at='2026-10-24T00:00:00Z',
                prerelease=True, assets=[asset]) | changes


def archive_bytes(extra=None):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as package:
        package.writestr('AutoQuestion/AutoQuestion.exe', b'synthetic fixture, never executed')
        package.writestr('AutoQuestion/_internal/test.txt', b'fixture')
        for name, value in (extra or {}).items():
            package.writestr(name, value)
    return output.getvalue()


class Response(io.BytesIO):
    def __init__(self, payload, url=RELEASES):
        super().__init__(payload)
        self.url = url


class UpdateTests(unittest.TestCase):
    def test_numeric_versions_prereleases_and_unordered_release_feed(self):
        versions = ['0.6.0alpha1', '0.6.0-beta.2', '0.6.0rc1', '0.6.0', '0.10.0', '1.0.0']
        self.assertEqual(sorted(reversed(versions), key=version_key), versions)
        for invalid in ('v1.0.0', '1.0', '01.0.0', '1.0.0/evil', '1.0.0;evil', '1.0.0\n'):
            with self.subTest(invalid=invalid), self.assertRaises(UpdateError): version_key(invalid)
        release = select_release([entry('0.10.0'), entry('0.6.0'), entry('0.3.0')], '0.5.0')
        self.assertEqual(release.version, '0.10.0')
        self.assertIsNone(select_release([entry('0.5.0'), entry('0.3.0')], '0.5.0'))
        self.assertEqual(select_release([entry('0.6.0-rc.1')], '0.5.0').version, '0.6.0-rc.1')

    def test_incomplete_draft_forged_asset_hash_size_and_repo_rejected(self):
        for changes in ({'digest': None}, {'digest': 'sha256:' + 'x' * 64}, {'size': True},
                        {'size': MAX_ARCHIVE + 1}, {'state': 'new'}, {'browser_download_url': 'https://evil.test/app.zip'}):
            data = entry(); data['assets'][0].update(changes)
            with self.subTest(changes=changes): self.assertIsNone(select_release([data], '0.5.0'))
        for data in (entry(draft=True), entry(published_at=None), entry(assets=[]), entry(assets=entry()['assets'] * 2)):
            self.assertIsNone(select_release([data], '0.5.0'))
        with self.assertRaises(UpdateError): select_release({'message': 'rate limited'})

    def test_network_allows_only_fixed_https_source_and_official_cdn(self):
        for url in (RELEASES, entry()['assets'][0]['browser_download_url'],
                    'https://release-assets.githubusercontent.com/path?signature=synthetic'):
            self.assertTrue(allowed_url(url))
        for url in ('http://api.github.com/', 'https://api.github.com/other', 'https://github.com/evil/repo/releases/download/x/a',
                    'https://github.com@evil.test/a', 'https://release-assets.githubusercontent.com.evil.test/a',
                    'https://objects.githubusercontent.com:444/a', 'https://objects.githubusercontent.com/a#fragment',
                    'https://user:password@objects.githubusercontent.com/a'):
            self.assertFalse(allowed_url(url))
            with self.assertRaises(UpdateError): ReleaseClient().open(url)
        with self.assertRaises(UpdateError):
            _Redirects().redirect_request(None, None, 302, '', {}, 'https://evil.test/app.zip')
        client = ReleaseClient(); client.opener = Mock()
        client.opener.open.return_value = Response(b'[]')
        self.assertIsNone(client.latest('0.5.0'))
        request = client.opener.open.call_args.args[0]
        self.assertNotIn('Authorization', request.headers)
        self.assertNotIn('X-autoquestion-token', request.headers)

    def test_download_verifies_hash_length_and_optional_checksums(self):
        payload = archive_bytes(); digest = hashlib.sha256(payload).hexdigest()
        release = Release('0.6.0', entry()['assets'][0]['browser_download_url'], len(payload), digest)
        with TemporaryDirectory() as directory:
            destination = Path(directory) / 'download.zip'
            client = ReleaseClient()
            client.open = Mock(side_effect=lambda url: Response(payload, url))
            client.download(release, destination, threading.Event(), lambda _: None)
            self.assertEqual(destination.read_bytes(), payload); destination.unlink()
            for wrong in (Release('0.6.0', release.url, len(payload), '0' * 64),
                          Release('0.6.0', release.url, len(payload) - 1, digest)):
                with self.assertRaises(UpdateError): client.download(wrong, destination, threading.Event(), lambda _: None)
                self.assertFalse(destination.exists())
            sums_payload = (digest + '  ' + release.url.rsplit('/', 1)[1] + '\n').encode()
            sums = Release('0.6.0', release.url.rsplit('/', 1)[0] + '/SHA256SUMS.txt', len(sums_payload), hashlib.sha256(sums_payload).hexdigest())
            with_sums = Release(release.version, release.url, release.size, release.digest, sums)
            client.open = lambda url: Response(sums_payload if url == sums.url else payload, url)
            client.download(with_sums, destination, threading.Event(), lambda _: None)
            destination.unlink()
            wrong_sums = b'0' * 64 + sums_payload[64:]
            client.open = lambda url: Response(wrong_sums if url == sums.url else payload, url)
            with self.assertRaises(UpdateError): client.download(with_sums, destination, threading.Event(), lambda _: None)
            self.assertFalse(destination.exists())

    def test_cancel_and_oversized_metadata_never_install(self):
        cancel = threading.Event(); cancel.set()
        release = Release('0.6.0', entry()['assets'][0]['browser_download_url'], 1, '0' * 64)
        client = ReleaseClient(); client.open = lambda url: Response(b'x', url)
        with TemporaryDirectory() as directory:
            with self.assertRaises(UpdateError): client.download(release, Path(directory) / 'x', cancel, lambda _: None)
            self.assertEqual(list(Path(directory).iterdir()), [])
        client.open = lambda url: Response(b' ' * (4 * 1024 * 1024 + 1))
        with self.assertRaises(UpdateError): client.latest('0.5.0')

    def test_zip_traversal_alias_symlink_and_incomplete_packages_rejected(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for index, name in enumerate(('../escape', '/AutoQuestion/escape', 'AutoQuestion/../escape', 'AutoQuestion/a\\b',
                         'AutoQuestion/C:evil', 'AutoQuestion/NUL.txt', 'AutoQuestion/COM¹.txt', 'AutoQuestion/LPT².txt',
                         'AutoQuestion/CONOUT$', 'AutoQuestion/file.',
                         'AutoQuestion/_INTERNAL/TEST.TXT')):
                with self.subTest(name=name):
                    archive = root / 'x.zip'
                    payload = archive_bytes({name.replace('\\', '/'): b'x'})
                    if '\\' in name: payload = payload.replace(name.replace('\\', '/').encode(), name.encode())
                    archive.write_bytes(payload)
                    target = root / str(index); target.mkdir()
                    with self.assertRaises(UpdateError): unpack_verified(archive, target, threading.Event())
                    self.assertEqual(list(target.iterdir()), [])
            archive = root / 'symlink.zip'
            with zipfile.ZipFile(archive, 'w') as package:
                link = zipfile.ZipInfo('AutoQuestion/link'); link.external_attr = (stat.S_IFLNK | 0o777) << 16
                package.writestr(link, '/elsewhere')
            with self.assertRaises(UpdateError): unpack_verified(archive, target, threading.Event())
            with zipfile.ZipFile(archive, 'w') as package: package.writestr('AutoQuestion/only.txt', b'x')
            with self.assertRaises(UpdateError): unpack_verified(archive, target, threading.Event())
            self.assertFalse((root / 'escape').exists())

    def test_manager_check_download_preserves_original_install_and_config(self):
        payload = archive_bytes()
        release = Release('0.6.0', entry()['assets'][0]['browser_download_url'], len(payload), hashlib.sha256(payload).hexdigest())
        client = ReleaseClient(); client.latest = Mock(return_value=release)
        client.open = lambda url: Response(payload, url)
        with TemporaryDirectory() as directory:
            root = Path(directory); old = root / '0.5.0'; old.mkdir(); (old / 'AutoQuestion.exe').write_text('old')
            config = root / 'config.json'; config.write_text('preserved config')
            manager = UpdateManager(client=client, root=root, current='0.5.0', install_supported=True)
            manager.check(); wait_until(lambda: manager.snapshot()['status'] == 'available')
            manager.check(); self.assertEqual(client.latest.call_count, 1)
            manager.download(); wait_until(lambda: manager.snapshot()['status'] == 'ready')
            downloaded = manager.target
            manager.last_check = 0; manager.check()
            wait_until(lambda: manager.snapshot()['status'] == 'ready')
            self.assertEqual(manager.target, downloaded)
            self.assertTrue((manager.target / 'AutoQuestion.exe').is_file())
            self.assertEqual(config.read_text(), 'preserved config')
            self.assertEqual((old / 'AutoQuestion.exe').read_text(), 'old')
            with patch('autoquestion.updates.subprocess.Popen') as launch:
                manager.launch_installer()
                self.assertEqual(launch.call_args.args[0][1], '--apply-update')
            manager.close()
            self.assertEqual(config.read_text(), 'preserved config')

    def test_installer_waits_and_changes_only_shortcut_then_launches(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); target = root / '9.0.0-aaaaaaaaaaaa'; target.mkdir()
            (target / 'AutoQuestion.exe').write_bytes(b'never executed'); (target / '_internal').mkdir()
            receipt = root / ('apply-' + 'a' * 32 + '.json')
            data = dict(version='9.0.0', target=str(target), parent=1234)
            receipt.write_text(json.dumps(data))
            calls = []
            apply_update(receipt, root=root, wait_parent=lambda pid: calls.append(('wait', pid)),
                         shortcut=lambda exe: calls.append(('shortcut', exe)), launcher=lambda *a, **k: calls.append(('launch', a)),
                         wait_ready=lambda *a: calls.append(('ready', None)))
            self.assertEqual([x[0] for x in calls], ['wait', 'launch', 'ready', 'shortcut'])
            self.assertFalse(receipt.exists())
            receipt.write_text(json.dumps(data))
            shortcut = Mock()
            with self.assertRaises(OSError):
                apply_update(receipt, root=root, wait_parent=lambda _: None, shortcut=shortcut, launcher=Mock(side_effect=OSError()))
            shortcut.assert_not_called()
            with self.assertRaises(UpdateError):
                apply_update(receipt, root=root, wait_parent=lambda _: None, shortcut=shortcut,
                             launcher=Mock(), wait_ready=Mock(side_effect=UpdateError('not healthy')))
            shortcut.assert_not_called()
            receipt.write_text(json.dumps(data | {'version': __version__}))
            with self.assertRaises(UpdateError): apply_update(receipt, root=root)
            receipt.write_text(json.dumps(data | {'target': str(root.parent)}))
            with self.assertRaises(UpdateError): apply_update(receipt, root=root)

    def test_shortcut_uses_encoded_literal_unicode_path_without_shell(self):
        target = Path("C:/合成路径/answer's $`folder/AutoQuestion.exe")
        with patch('autoquestion.updates.subprocess.run') as run:
            _shortcut(target)
        command = run.call_args.args[0]
        self.assertIn('-EncodedCommand', command)
        script = base64.b64decode(command[-1]).decode('utf-16-le')
        self.assertIn("answer''s $`folder", script)
        self.assertNotIn('shell', run.call_args.kwargs)

    def test_ui_install_requires_stopped_runner_and_update_failures_are_isolated(self):
        with TemporaryDirectory() as directory:
            updater = Mock(); updater.snapshot.return_value = {'status': 'available'}
            controller = UIController(store=UserConfigStore(Path(directory) / 'config.json'), updater=updater)
            try:
                self.assertEqual(controller.state()['update'], {'status': 'available'})
                controller.thread = Mock(); controller.thread.is_alive.return_value = True
                with self.assertRaises(UIError): controller.update_install()
                updater.launch_installer.assert_not_called()
                controller.thread.is_alive.return_value = False
                self.assertEqual(controller.update_install(), {'installing': True})
                updater.launch_installer.assert_called_once()
                updater.download.side_effect = UpdateError('合成失败')
                with self.assertRaises(UIError): controller.update_download()
            finally: controller.close()
            updater.close.assert_called()


if __name__ == '__main__': unittest.main()
