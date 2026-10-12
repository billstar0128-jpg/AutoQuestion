"""Authenticated loopback UI; shares the existing runner and secure config store."""
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import logging
from pathlib import Path
import secrets
import threading
import time
import webbrowser

from pydantic import SecretStr, ValidationError

from . import __version__
from .config import ConfigError, load_config, load_llm_config
from .credentials import CredentialError, WindowsCredentials
from .provider_presets import get_preset, public_presets
from .setup_wizard import save_configuration
from .startup import RuntimeSettings
from .user_config import UserConfig, UserConfigError, UserConfigStore

ASSETS = Path(__file__).parent / 'web'
MAX_BODY = 16384


class UIError(ValueError):
    """Fixed, safe user-facing failures; never raw validation/request content."""


class UIEvents(logging.Handler):
    def __init__(self, controller):
        super().__init__(logging.INFO)
        self.controller = controller

    def emit(self, record):
        self.controller.record(record)


class UIController:
    def __init__(self, *, store=None, backend=None, run_app=None):
        self.store = UserConfigStore() if store is None else store
        self.backend = WindowsCredentials() if backend is None else backend
        if run_app is None:
            from .app import main as run_app
        self.run_app = run_app
        self.lock = threading.RLock()
        self.runner = self.bridge = self.thread = None
        self.cancel = threading.Event()
        self.session_secret = None
        self.secret_scope = None
        self.history = []
        self.events = []
        self.error = ''
        self.route = ''
        self.started = None
        self.active_profile = ''
        self.active_mode = ''
        self.handler = UIEvents(self)
        logging.getLogger('autoquestion').addHandler(self.handler)

    def _saved(self):
        try:
            return self.store.load()
        except UserConfigError:
            raise UIError('保存的配置无法读取。请在设置页重新配置；确认保存前原文件保持不变。') from None

    def _has_key(self, config):
        if config.protocol_provider == 'fake':
            return True
        if self.session_secret is not None and self.secret_scope == (config.provider_profile, config.base_url):
            return True
        try:
            return config.credential_mode == 'stored' and self.backend.exists(config.credential_id)
        except CredentialError:
            return False

    def state(self):
        with self.lock:
            try:
                saved = self._saved()
                config_error = ''
            except UIError as exc:
                saved, config_error = None, str(exc)
            public = None
            if saved:
                public = saved.model_dump(exclude={'credential_id'}) | {'has_key': self._has_key(saved)}
            active = bool(self.thread and self.thread.is_alive())
            status = self.runner.state.value if self.runner else ('STARTING' if active else 'STOPPED')
            return dict(version=__version__, config=public, active=active, status=status,
                        bridge_available=active and self.bridge is not None,
                        error=self.error or config_error, route=self.route,
                        active_profile=self.active_profile if active else '',
                        active_mode=self.active_mode if active else '',
                        history=list(self.history), events=list(self.events))

    def _require_stopped(self):
        if self.thread and self.thread.is_alive():
            raise UIError('请先停止答题，等待任务清理完成后再修改配置。')

    def configure(self, body):
        allowed = {'provider_profile', 'base_url', 'model', 'supports_vision', 'input_mode',
                   'credential_mode', 'api_key'}
        if not isinstance(body, dict) or set(body) - allowed:
            raise UIError('配置字段无效。')
        with self.lock:
            self._require_stopped()
            try:
                preset = get_preset(body.get('provider_profile'))
                if preset.protocol_provider == 'fake':
                    config = UserConfig(provider_profile=preset.id, protocol_provider='fake',
                                        credential_mode='none', input_mode='demo')
                    result = save_configuration(self.store, self.backend, config)
                    self.session_secret = self.secret_scope = None
                else:
                    raw = body.get('api_key', '')
                    if not isinstance(raw, str) or len(raw.encode('utf-8')) > 2560 or any(ord(c) < 32 or ord(c) == 127 for c in raw):
                        raise UIError('API Key 格式无效；请重新输入。')
                    secret = SecretStr(raw.strip()) if raw.strip() else None
                    config = UserConfig(provider_profile=preset.id, protocol_provider=preset.protocol_provider,
                                        base_url=body.get('base_url', ''), model=body.get('model', ''),
                                        supports_vision=body.get('supports_vision', False),
                                        input_mode=body.get('input_mode', 'auto'),
                                        credential_mode='session')
                    mode = body.get('credential_mode', 'stored')
                    if mode not in {'stored', 'session'}:
                        raise UIError('请选择安全保存或仅本次使用。')
                    try:
                        previous = self._saved()
                    except UIError:
                        previous = None
                    scope = (config.provider_profile, config.base_url)
                    same = previous and (previous.provider_profile, previous.base_url) == scope
                    if secret is None and mode == 'stored' and same and previous.credential_mode == 'stored' and self._has_key(previous):
                        config = config.model_copy(update={'credential_mode': 'stored', 'credential_id': previous.credential_id})
                    else:
                        if secret is None and mode == 'session' and self.secret_scope == scope:
                            secret = self.session_secret
                        if secret is None:
                            raise UIError('请填写 API Key；更换服务商或地址时必须重新输入。')
                        if secret.get_secret_value() in config.model_dump_json():
                            raise UIError('API Key 不能放在地址或模型等普通配置字段中。')
                        config = config.model_copy(update={'credential_mode': mode})
                    result = save_configuration(self.store, self.backend, config, secret)
                    self.session_secret = result.session_secret
                    self.secret_scope = scope if result.session_secret is not None else None
                self.error = ''
                return {'saved': True}
            except UIError:
                raise
            except CredentialError:
                raise UIError('Windows 安全凭据保存不可用。原配置保持不变，可改选“仅本次使用”。') from None
            except (ConfigError, ValidationError, TypeError, ValueError):
                raise UIError('配置未保存。请检查 API 根地址、模型 ID 和输入方式，不要把 URL 与模型填反。') from None

    def start(self, body):
        if (not isinstance(body, dict) or set(body) - {'open_demo', 'offline_demo'}
                or any(type(body.get(key, False)) is not bool for key in ('open_demo', 'offline_demo'))):
            raise UIError('启动参数无效。')
        with self.lock:
            self._require_stopped()
            saved = (UserConfig(provider_profile='offline_demo', protocol_provider='fake',
                                credential_mode='none', input_mode='demo') if body.get('offline_demo') else self._saved())
            if saved is None:
                raise UIError('请先完成首次配置，或选择离线 Demo。')
            config = load_config(saved.to_env())
            if saved.protocol_provider != 'fake':
                secret = self.session_secret if self.secret_scope == (saved.provider_profile, saved.base_url) else None
                if secret is None and saved.credential_mode == 'stored':
                    try:
                        secret = self.backend.get(saved.credential_id)
                    except CredentialError:
                        raise UIError('安全凭据无法读取，请在设置页重新输入 Key 或选仅本次使用。') from None
                if secret is None:
                    raise UIError('请在设置页填写本次 API Key。')
                config = replace(config, llm_config=load_llm_config(saved.to_env() | {'LLM_API_KEY': secret.get_secret_value()}))
            if body.get('open_demo') and config.input_mode == 'demo':
                raise UIError('固定离线 Demo 不需要打开浏览器。')
            runtime = RuntimeSettings(config, saved.display_name or get_preset(saved.provider_profile).display_name,
                                      saved.credential_mode)
            from .cli import parse_args
            args = parse_args(['--open-demo'] if body.get('open_demo') else [])
            self.cancel.clear()
            self.error = self.route = ''
            self.runner = self.bridge = None
            self.active_profile = get_preset(saved.provider_profile).display_name
            self.active_mode = saved.input_mode
            def ready(runner, bridge):
                with self.lock:
                    self.runner, self.bridge = runner, bridge
                if self.cancel.is_set():
                    runner.stop()
            def run():
                try:
                    code = self.run_app(parsed_args=args, runtime=runtime, on_ready=ready)
                    if code:
                        with self.lock:
                            self.error = self.error or '启动失败。请关闭旧实例，检查热键占用与配置后重试。'
                except Exception:
                    with self.lock:
                        self.error = '答题服务启动失败，请检查本机环境后重试。'
                finally:
                    with self.lock:
                        self.bridge = None
            self.thread = threading.Thread(target=run, name='autoquestion-ui-hotkeys', daemon=False)
            self.thread.start()
            return {'started': True}

    def stop(self):
        self.cancel.set()
        with self.lock:
            runner = self.runner
        if runner:
            runner.stop()
        return {'stopping': True}

    def pair(self):
        with self.lock:
            if self.bridge is None or self.cancel.is_set():
                raise UIError('请用 AUTO 或 DOM 启动答题后再获取配对码。')
            return {'code': self.bridge.pairing_code()}

    def clear(self):
        with self.lock:
            self.history.clear()
            self.events.clear()
            self.error = ''
        return {'cleared': True}

    def record(self, record):
        with self.lock:
            if hasattr(record, 'question_result') and hasattr(record, 'answer_result'):
                self.history.insert(0, dict(question=record.question_result, answer=record.answer_result,
                                           time=time.strftime('%H:%M:%S')))
                del self.history[20:]
                self.error = ''
            text = record.getMessage()
            if text.startswith('Triggered #'):
                self.error = self.route = ''
            if text.startswith('Input:'):
                self.route = 'VISION' if 'VISION' in text else 'DOM'
            if record.levelno >= logging.WARNING:
                # Existing app emits fixed safe diagnostics, never SDK exception bodies.
                self.events.insert(0, text[:600])
                del self.events[20:]
                if record.levelno >= logging.ERROR:
                    self.error = text[:600]

    def close(self):
        self.stop()
        if self.thread:
            self.thread.join()
        logging.getLogger('autoquestion').removeHandler(self.handler)
        with self.lock:
            self.history.clear()
            self.events.clear()
            self.session_secret = self.secret_scope = None


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError()
        result[key] = value
    return result


class UIServer(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, controller, *, port=0):
        self.controller = controller
        self.token = secrets.token_urlsafe(32)
        super().__init__(('127.0.0.1', port), UIHandler)
        self.origin = f'http://127.0.0.1:{self.server_port}'

    def close(self):
        self.server_close()
        self.controller.close()
        self.token = ''


class UIHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # No request, bearer token, configuration or question logs on disk.

    def _reply(self, code, body, content_type='application/json; charset=utf-8'):
        payload = json.dumps(body, ensure_ascii=False).encode('utf-8') if isinstance(body, dict) else body
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _allowed(self, api=False):
        expected = f'127.0.0.1:{self.server.server_port}'
        if self.headers.get('Host') != expected:
            self._reply(403, {'error': '本机地址无效。'})
            return False
        origin = self.headers.get('Origin')
        if origin and origin != self.server.origin:
            self._reply(403, {'error': '请求来源无效。'})
            return False
        token = self.headers.get('X-AutoQuestion-Token', '')
        if api and (not token.isascii() or not hmac.compare_digest(token, self.server.token)):
            self._reply(403, {'error': '请通过 AutoQuestion 双击启动入口重新打开界面。'})
            return False
        return True

    def do_GET(self):
        if not self._allowed(self.path.startswith('/api/')):
            return
        if self.path == '/api/state':
            return self._reply(200, self.server.controller.state())
        if self.path == '/api/providers':
            return self._reply(200, {'providers': public_presets(), 'checked': '2026-10-13'})
        files = {'/': ('index.html', 'text/html; charset=utf-8'),
                 '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                 '/style.css': ('style.css', 'text/css; charset=utf-8')}
        if self.path in files:
            name, mime = files[self.path]
            return self._reply(200, (ASSETS / name).read_bytes(), mime)
        self._reply(404, {'error': '页面不存在。'})

    def do_POST(self):
        self.connection.settimeout(5)
        if not self._allowed(True):
            return
        if self.headers.get('Origin') != self.server.origin or self.headers.get('Content-Type') != 'application/json':
            return self._reply(403, {'error': '请求来源或格式无效。'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= MAX_BODY or self.headers.get('Transfer-Encoding'):
                return self._reply(413, {'error': '请求大小无效。'})
            data = json.loads(self.rfile.read(length), object_pairs_hook=_unique_object,
                              parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            if not isinstance(data, dict):
                raise ValueError()
        except (ValueError, UnicodeError, OSError):
            return self._reply(400, {'error': '请求格式无效。'})
        actions = {'/api/config': lambda: self.server.controller.configure(data),
                   '/api/start': lambda: self.server.controller.start(data),
                   '/api/stop': self.server.controller.stop,
                   '/api/pair': self.server.controller.pair,
                   '/api/clear': self.server.controller.clear}
        if self.path == '/api/shutdown' and not data:
            self._reply(200, {'closing': True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        if self.path not in actions:
            return self._reply(404, {'error': '操作不存在。'})
        if self.path not in {'/api/config', '/api/start'} and data:
            return self._reply(400, {'error': '操作参数无效。'})
        try:
            self._reply(200, actions[self.path]())
        except UIError as exc:
            self._reply(400, {'error': str(exc)})
        except Exception:
            self._reply(500, {'error': '本机操作未完成，请检查配置或重启控制台。'})


def main():
    logging.basicConfig(level=logging.INFO, handlers=[logging.NullHandler()])
    server = UIServer(UIController())
    url = server.origin + '/#session=' + server.token
    try:
        if not webbrowser.open(url):
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showinfo('AutoQuestion', '请在浏览器打开：\n' + url)
            root.destroy()
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.close()
    return 0
