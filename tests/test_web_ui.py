"""Loopback UI and credential tests use temp settings and synthetic data only."""
import ctypes
from ctypes import wintypes
import http.client
import json
import logging
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import threading
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from autoquestion.app import Status, TaskRunner
from autoquestion.config import Config
from autoquestion.demo import make_demo_callback
from autoquestion.provider_presets import PRESETS, public_presets
from autoquestion.user_config import UserConfigStore
from autoquestion.web_ui import UIController, UIError, UIServer
from test_core import wait_until
from test_setup import FakeCredentials, SECRET


def simulated_app(*, runtime, on_ready, **kwargs):
    runner = TaskRunner(callback=make_demo_callback(runtime.config))
    try:
        runner.ready()
        on_ready(runner, None)
        runner.trigger()
        runner.stop_event.wait(5)
    finally:
        runner.close()
    return 0


class WebUITests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.backend = FakeCredentials()
        self.store = UserConfigStore(Path(self.directory.name) / 'config.json')
        self.controller = UIController(store=self.store, backend=self.backend, run_app=simulated_app)
        self.addCleanup(self.controller.close)
        self.logger = logging.getLogger('autoquestion')
        level = self.logger.level
        self.logger.setLevel(logging.INFO)
        self.addCleanup(self.logger.setLevel, level)
        self.server = UIServer(self.controller)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(3)

    def request(self, path, body=None, *, headers=None, raw=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        request_headers = {'X-AutoQuestion-Token': self.server.token}
        if body is not None or raw is not None:
            request_headers.update(Origin=self.server.origin, **{'Content-Type': 'application/json'})
        request_headers.update(headers or {})
        payload = json.dumps(body) if body is not None else raw
        connection.request('POST' if payload is not None else 'GET', path, body=payload, headers=request_headers)
        response = connection.getresponse()
        code, data, result_headers = response.status, response.read(), dict(response.getheaders())
        connection.close()
        return code, data, result_headers

    def config(self, **changes):
        return dict(provider_profile='deepseek', base_url='https://api.deepseek.com', model='deepseek-flash',
                    supports_vision=True, input_mode='auto', credential_mode='session', api_key=SECRET) | changes

    def test_host_token_origin_content_type_and_body_guards(self):
        for path, body, headers in (
                ('/api/state', None, {'X-AutoQuestion-Token': ''}),
                ('/api/state', None, {'Host': 'evil.example'}),
                ('/', None, {'Host': 'evil.example'}),
                ('/api/config', self.config(), {'Origin': 'https://evil.example'}),
                ('/api/config', self.config(), {'Content-Type': 'text/plain'})):
            with self.subTest(path=path, headers=headers):
                self.assertEqual(self.request(path, body, headers=headers)[0], 403)
        self.assertEqual(self.request('/api/config', raw='x' * 16385)[0], 413)
        self.assertEqual(self.request('/api/config', raw='{"api_key":"test-x","api_key":"test-y"}')[0], 400)
        self.assertEqual(self.request('/api/config', raw='{"bad":NaN}')[0], 400)
        self.assertEqual(self.request('/api/config', body=[])[0], 400)
        self.assertFalse(self.store.path.exists())
        self.assertEqual(self.backend.calls, [])

    def test_assets_are_fixed_and_csp_prevents_external_script_and_frames(self):
        for path in ('/', '/style.css', '/app.js'):
            with self.subTest(path=path):
                code, body, headers = self.request(path)
                self.assertEqual(code, 200)
                self.assertTrue(body)
                self.assertIn("script-src 'self'", headers['Content-Security-Policy'])
                self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])
                self.assertEqual(headers['Cache-Control'], 'no-store')
        for path in ('/../.env', '/config.json', '/api/state?token=secret', '/web_ui.py'):
            self.assertEqual(self.request(path)[0], 404)

    def test_session_save_never_stores_or_returns_key_and_preserves_after_restart(self):
        self.assertEqual(self.request('/api/config', self.config())[0], 200)
        self.assertNotIn(SECRET, self.store.path.read_text())
        response = self.request('/api/state')[1].decode()
        self.assertNotIn(SECRET, response)
        self.assertNotIn('credential_id', response)
        self.assertTrue(json.loads(response)['config']['has_key'])
        fresh = UIController(store=self.store, backend=self.backend, run_app=simulated_app)
        try:
            self.assertFalse(fresh.state()['config']['has_key'])
            with self.assertRaises(UIError):
                fresh.start({})
        finally:
            fresh.close()

    def test_safe_storage_reuse_requires_same_endpoint_and_copy_on_write_rollback(self):
        self.controller.configure(self.config(credential_mode='stored'))
        first = self.store.load()
        self.controller.configure(self.config(credential_mode='stored', api_key=''))
        self.assertEqual(self.store.load().credential_id, first.credential_id)
        with self.assertRaises(UIError):
            self.controller.configure(self.config(base_url='https://other.example/v1', credential_mode='stored', api_key=''))
        self.backend.fail_write = True
        with self.assertRaises(UIError):
            self.controller.configure(self.config(credential_mode='stored', api_key='test-replacement-value'))
        self.assertEqual(self.store.load(), first)
        self.assertEqual(len(self.backend.items), 1)

    def test_invalid_fields_are_redacted_and_do_not_replace_settings(self):
        self.controller.configure(self.config())
        before = self.store.path.read_bytes()
        for changes in ({'model': 'https://example.com?key=' + SECRET}, {'base_url': 'model-name'},
                        {'supports_vision': 'true'}, {'extra_field': SECRET}):
            with self.subTest(changes=changes):
                code, body, _ = self.request('/api/config', self.config(**changes))
                self.assertEqual(code, 400)
                self.assertNotIn(SECRET, body.decode())
                self.assertEqual(self.store.path.read_bytes(), before)

    def test_demo_uses_real_callback_results_and_restart_without_changing_api_config(self):
        self.controller.configure(self.config())
        before = self.store.path.read_bytes()
        for _ in range(2):
            self.assertEqual(self.request('/api/start', {'offline_demo': True})[0], 200)
            wait_until(lambda: bool(self.controller.state()['history']) and self.controller.runner.state == Status.READY)
            answer = self.controller.state()['history'][0]
            self.assertEqual(answer['answer']['selected_text'], '巴黎')
            self.assertEqual(self.request('/api/config', self.config())[0], 400)
            self.assertEqual(self.request('/api/start', {'offline_demo': True})[0], 400)
            self.assertEqual(self.request('/api/stop', {})[0], 200)
            wait_until(lambda: not self.controller.state()['active'])
            self.assertEqual(self.store.path.read_bytes(), before)
        self.controller.clear()
        self.assertEqual(self.controller.state()['history'], [])

    def test_provider_examples_have_valid_urls_models_and_keep_defaults_empty(self):
        from autoquestion.config import validate_model_id, validate_base_url
        for preset in PRESETS.values():
            self.assertEqual(preset.suggested_model, '')
            self.assertFalse(preset.default_supports_vision)
            for model in preset.example_models:
                self.assertEqual(validate_model_id(model), model)
            if preset.default_base_url:
                self.assertEqual(validate_base_url(preset.default_base_url), preset.default_base_url)
        public = json.loads(self.request('/api/providers')[1])['providers']
        self.assertEqual(public, public_presets())
        self.assertEqual(public[0]['models'], ['deepseek-flash', 'deepseek-v4-pro'])

    def test_double_click_launcher_hands_off_to_pythonw_then_opens_ui(self):
        import importlib.util
        from importlib.machinery import SourceFileLoader
        from types import SimpleNamespace
        from unittest.mock import patch
        entry = Path(__file__).resolve().parents[1] / 'AutoQuestion.pyw'
        loader = SourceFileLoader('autoquestion_test_launcher', str(entry))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        launcher = importlib.util.module_from_spec(spec)
        loader.exec_module(launcher)
        launcher.ROOT = Path(self.directory.name)
        scripts = launcher.ROOT / '.venv-win/Scripts'
        scripts.mkdir(parents=True)
        for name in ('pythonw.exe', 'python.exe'):
            (scripts / name).touch()
        with patch('subprocess.Popen') as child:
            launcher.launch()
            self.assertEqual(child.call_args.args[0], [str(scripts / 'pythonw.exe'), str(entry)])
        with patch.object(sys, 'prefix', str(launcher.ROOT / '.venv-win')), \
             patch('subprocess.run', return_value=SimpleNamespace(returncode=0)), \
             patch('autoquestion.web_ui.main') as open_ui:
            launcher.launch()
            open_ui.assert_called_once_with()


@unittest.skipUnless(sys.platform == 'win32', 'Windows only')
@unittest.skipIf(os.environ.get('AUTOQUESTION_CI') == '1', 'Local desktop UI hotkey test')
class NativeWebUITests(unittest.TestCase):
    def test_real_f8_answer_esc_cleanup_and_ui_restart(self):
        with TemporaryDirectory() as directory:
            controller = UIController(store=UserConfigStore(Path(directory) / 'config.json'), backend=FakeCredentials())
            logger = logging.getLogger('autoquestion')
            previous = logger.level
            logger.setLevel(logging.INFO)
            try:
                post = ctypes.WinDLL('user32', use_last_error=True).PostThreadMessageW
                post.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
                post.restype = wintypes.BOOL
                # Capture actual native IDs without sending input to user windows.
                from autoquestion.hotkeys import WindowsHotkeys, WM_HOTKEY
                from unittest.mock import patch
                original = WindowsHotkeys.listen
                hotkeys = []
                def listen(native, runner):
                    hotkeys.append(native)
                    original(native, runner)
                with patch.object(WindowsHotkeys, 'listen', listen):
                    for index in range(2):
                        controller.start({'offline_demo': True})
                        wait_until(lambda: len(hotkeys) == index + 1)
                        self.assertTrue(post(controller.thread.native_id, WM_HOTKEY, hotkeys[-1].analyze_id, 0))
                        wait_until(lambda: len(controller.state()['history']) == index + 1)
                        self.assertEqual(controller.state()['history'][0]['answer']['selected_text'], '巴黎')
                        self.assertTrue(post(controller.thread.native_id, WM_HOTKEY, hotkeys[-1].exit_id, 0))
                        wait_until(lambda: not controller.state()['active'])
                self.assertFalse(controller.store.path.exists())
            finally:
                controller.close()
                logger.setLevel(previous)


if __name__ == '__main__':
    unittest.main()
