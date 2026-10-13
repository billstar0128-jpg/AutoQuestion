"""Explicit executable check: temp configuration, own hotkeys and a local Fake API."""
import ctypes
from ctypes import wintypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import http.client
import json
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import time

from . import __version__


def run(report_path):
    logging.basicConfig(level=logging.INFO, handlers=[logging.NullHandler()])
    results = {'version': __version__, 'passed': False, 'checks': []}
    try:
        from pydantic import SecretStr
        from .config import LLMConfig
        from .hotkeys import WindowsHotkeys, WM_HOTKEY
        from .llm.fake import FakeLLMProvider, demo_question
        from .llm.openai_compatible import OpenAICompatibleProvider
        from .user_config import UserConfigStore
        from .web_ui import UIController, UIServer
        from .browser_bridge import BrowserBridge
        from .resources import resource_root
        from mss.windows import MSS
        import ssl
        ssl.create_default_context()
        with MSS() as capture:
            assert capture.monitors
        results['checks'].append('native capture imports and TLS available; no screenshot taken')
        assert (resource_root() / 'extension/manifest.json').is_file()
        assert (resource_root() / 'examples/demo_quiz.html').is_file()
        assert (resource_root() / 'autoquestion/web/index.html').is_file() if getattr(__import__('sys'), 'frozen', False) else True
        answer_json = FakeLLMProvider().answer_question(demo_question()).model_dump_json()
        class FakeAPI(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                data = json.dumps({'id': 'test-completion', 'object': 'chat.completion', 'created': 0,
                                   'model': 'test-model', 'choices': [{'index': 0, 'finish_reason': 'stop',
                                   'message': {'role': 'assistant', 'content': answer_json}}]}).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        api = ThreadingHTTPServer(('127.0.0.1', 0), FakeAPI)
        api_thread = threading.Thread(target=api.serve_forever, daemon=True)
        api_thread.start()
        try:
            provider = OpenAICompatibleProvider(LLMConfig(SecretStr('test-frozen-key'),
                                               f'http://127.0.0.1:{api.server_port}/v1', 'test-model'))
            assert provider.answer_question(demo_question()).selected_text == '巴黎'
            results['checks'].append('real SDK to synthetic loopback API; no paid request')
        finally:
            api.shutdown()
            api.server_close()
            api_thread.join(3)
        bridge = BrowserBridge(port=0)
        try:
            bridge.start()
            assert bridge.pairing_code()
            results['checks'].append('compiled WebSocket bridge bind and cleanup')
        finally:
            bridge.close()
        with TemporaryDirectory(prefix='autoquestion-self-test-') as directory:
            store = UserConfigStore(Path(directory) / 'config.json')
            controller = UIController(store=store)
            server = UIServer(controller)
            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            original = WindowsHotkeys.listen
            native = []
            def listen(hotkeys, runner):
                native.append(hotkeys)
                original(hotkeys, runner)
            WindowsHotkeys.listen = listen
            def request(path, body=None):
                connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                headers = {'X-AutoQuestion-Token': server.token}
                if body is not None:
                    headers |= {'Origin': server.origin, 'Content-Type': 'application/json'}
                connection.request('POST' if body is not None else 'GET', path,
                                   json.dumps(body) if body is not None else None, headers)
                response = connection.getresponse()
                data = response.read()
                connection.close()
                assert response.status == 200
                return json.loads(data) if path.startswith('/api/') else data
            def until(predicate):
                deadline = time.monotonic() + 10
                while not predicate():
                    if time.monotonic() >= deadline:
                        raise RuntimeError('self-test wait failed')
                    time.sleep(0.03)
            try:
                assert b'API Key' in request('/')
                request('/api/config', dict(provider_profile='deepseek', base_url='https://api.deepseek.com',
                                           model='deepseek-flash', supports_vision=True, input_mode='auto',
                                           credential_mode='session', api_key='test-frozen-key'))
                assert request('/api/state')['config']['has_key']
                assert 'test-frozen-key' not in store.path.read_text()
                results['checks'].append('real HTTP configuration save, key redaction and assets')
                post = ctypes.WinDLL('user32', use_last_error=True).PostThreadMessageW
                post.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
                post.restype = wintypes.BOOL
                for index in range(2):
                    request('/api/start', {'offline_demo': True})
                    until(lambda: len(native) == index + 1)
                    assert post(controller.thread.native_id, WM_HOTKEY, native[-1].analyze_id, 0)
                    until(lambda: len(controller.state()['history']) == index + 1)
                    assert controller.state()['history'][0]['answer']['selected_text'] == '巴黎'
                    assert post(controller.thread.native_id, WM_HOTKEY, native[-1].exit_id, 0)
                    until(lambda: not controller.state()['active'])
                results['checks'].append('real F8 / Fake answer / ESC / restart; own thread messages only')
            finally:
                WindowsHotkeys.listen = original
                server.shutdown()
                server.server_close()
                server_thread.join(3)
                controller.close()
        results['passed'] = True
    except Exception:
        results['error'] = 'Executable self-test failed; no raw exception or credentials recorded.'
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if results['passed'] else 1
