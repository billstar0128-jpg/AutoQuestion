"""Authenticated loopback transport. No browser is launched and no content is polled."""
from dataclasses import dataclass, field
import hmac
import logging
import re
import secrets
import threading
import time

from .bridge_protocol import VERSION, PORT, MAX_BYTES, ProtocolError, decode_message, encode_message
from .browser_identity import ProcessIdentity, browser_peer
from .capture.browser import BrowserExtractionError, question_from_dom
from .capture.screen import CaptureError

LOGGER = logging.getLogger('autoquestion')
# Third-party debug logs contain frames/headers. Never forward them to application logs.
TRANSPORT_LOG = logging.Logger('autoquestion.bridge.transport', level=logging.CRITICAL + 1)
TRANSPORT_LOG.addHandler(logging.NullHandler())
TRANSPORT_LOG.propagate = False


@dataclass(eq=False)
class _Session:
    socket: object = field(repr=False)
    identity: ProcessIdentity
    state: tuple | None = None
    request: str | None = None
    reply: dict | None = field(default=None, repr=False)
    alive: bool = True
    retired: str | None = None


@dataclass(frozen=True)
class BrowserPin:
    session: _Session = field(repr=False)
    state: tuple


class BrowserBridge:
    def __init__(self, *, port=PORT, resolver=browser_peer, timeout=1.5):
        self.port, self._resolver, self.timeout = port, resolver, timeout
        self._secret = secrets.token_urlsafe(24)
        self._condition = threading.Condition()
        self._sessions = []
        self._connections = set()
        self._handlers = set()
        self._server = self._thread = None
        self._closed = False

    def start(self):
        from websockets.sync.server import serve
        self._server = serve(self._handle, '127.0.0.1', self.port,
                             origins=[re.compile(r'chrome-extension://[a-p]{32}')],
                             process_request=self._guard, compression=None, open_timeout=2,
                             ping_interval=20, ping_timeout=20, close_timeout=0.2,
                             max_size=MAX_BYTES, max_queue=4, logger=TRANSPORT_LOG, server_header=None)
        self.port = self._server.socket.getsockname()[1]
        self._thread = threading.Thread(target=self._server.serve_forever, name='browser-dom-bridge')
        self._thread.start()
        LOGGER.info('Browser DOM Bridge: waiting (127.0.0.1:%d)', self.port)

    def _guard(self, connection, request):
        try:
            allowed = (not self._closed and request.path == '/bridge'
                       and request.headers['Host'] == f'127.0.0.1:{self.port}'
                       and connection.remote_address[0] == '127.0.0.1')
        except Exception:
            allowed = False
        if not allowed:
            return connection.respond(403, 'Forbidden\n')

    def _handle(self, connection):
        session = None
        thread = threading.current_thread()
        with self._condition:
            if self._closed or len(self._connections) >= 8:
                connection.close(1008, 'Unavailable')
                return
            self._connections.add(connection)
            self._handlers.add(thread)
        try:
            hello = decode_message(connection.recv(timeout=2))
            if hello['type'] != 'hello' or not hmac.compare_digest(hello['token'], self._secret):
                raise ProtocolError()
            identity = self._resolver(connection.remote_address[1], self.port)
            session = _Session(connection, identity)
            with self._condition:
                if self._closed:
                    return
                self._sessions.append(session)
            connection.send(encode_message(dict(v=VERSION, type='ready')))
            LOGGER.info('Browser DOM Bridge: connected')
            for raw in connection:
                message = decode_message(raw)
                with self._condition:
                    if message['type'] == 'state':
                        state = (message['epoch'], message['window'], message['tab'])
                        if session.state and (state[0] < session.state[0] or
                                              (state[0] == session.state[0] and state != session.state)):
                            raise ProtocolError()
                        session.state = state
                    elif message['type'] == 'result':
                        if message['request'] == session.retired:
                            continue  # Late response to the last timed-out request; never consume it.
                        if message['request'] != session.request or session.reply is not None:
                            raise ProtocolError()
                        session.reply = message
                    elif message['type'] != 'pong':
                        raise ProtocolError()
                    self._condition.notify_all()
        except Exception:
            # Only fixed errors; never log incoming messages, token, URL or exceptions.
            connection.close(1008, 'Bridge session ended')
        finally:
            with self._condition:
                if session:
                    session.alive = False
                    if session in self._sessions:
                        self._sessions.remove(session)
                self._connections.discard(connection)
                self._handlers.discard(thread)
                self._condition.notify_all()
            if session and not self._closed:
                LOGGER.info('Browser DOM Bridge: disconnected')

    def pin(self, target):
        """Snapshot only in-memory metadata at F8; no DOM request here."""
        identity = ProcessIdentity(target.process_id, target.executable, target.process_started)
        with self._condition:
            matches = [s for s in self._sessions if s.identity == identity and s.alive
                       and s.state is not None and s.state[1] >= 0]
            return BrowserPin(matches[0], matches[0].state) if len(matches) == 1 else None

    def extract_for_target(self, target, verify, pin):
        verify()
        reply = self._request(pin, 'extract')
        if reply['status'] != 'ok':
            raise BrowserExtractionError('Browser DOM unavailable: permission or readable question missing.')
        verify()
        data = reply['question']
        return question_from_dom(dict(kind=data['kind'], question_text=data['stem'], options=data['options']))

    def verify_pin(self, pin):
        """Metadata-only round trip, also used around fallback pixels. Fail closed on disconnect."""
        try:
            if self._request(pin, 'check')['status'] != 'unchanged':
                raise CaptureError('无法确认浏览器仍是 F8 时的标签，已取消截图。')
        except BrowserExtractionError:
            raise CaptureError('浏览器连接中断，无法确认原标签；请重新按 F8。') from None

    def _request(self, pin, operation):
        if pin is None:
            raise BrowserExtractionError('Browser DOM unavailable: no matching extension session.')
        session = pin.session
        with self._condition:
            if not session.alive:
                raise BrowserExtractionError('Browser DOM unavailable: extension disconnected.')
            if session.state != pin.state:
                raise CaptureError('浏览器窗口或标签已变化，请重新按 F8。')
            session.request, session.reply = secrets.token_hex(16), None
            request = dict(v=VERSION, type=operation, request=session.request,
                           epoch=pin.state[0], window=pin.state[1], tab=pin.state[2])
        try:
            session.socket.send(encode_message(request))
            deadline = time.monotonic() + self.timeout
            with self._condition:
                while session.alive and session.reply is None and session.state == pin.state:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    self._condition.wait(remaining)
                if session.state != pin.state:
                    raise CaptureError('浏览器窗口或标签已变化，请重新按 F8。')
                reply = session.reply
                if reply is None:
                    raise BrowserExtractionError('Browser DOM unavailable: extension response timed out.')
                if reply['status'] == 'changed':
                    raise CaptureError('浏览器目标已变化，请保持原题在前台后重试。')
            return reply
        except (CaptureError, BrowserExtractionError):
            raise
        except Exception:
            raise BrowserExtractionError('Browser DOM unavailable: connection failed.') from None
        finally:
            with self._condition:
                session.retired = session.request
                session.request, session.reply = None, None

    def pair_dialog(self):
        """Explicit local UI only. No secret in console, arguments, files or config."""
        import tkinter as tk
        root = tk.Tk()
        root.title('AutoQuestion Browser DOM pairing')
        tk.Label(root, text='在扩展弹窗输入本次配对码。关闭此窗口后回到 READY。\n'
                 '配对码只在本次运行有效，不要发到聊天或 Issue。', padx=24, pady=18).pack()
        value = tk.StringVar(root, self._secret)
        entry = tk.Entry(root, textvariable=value, width=40, state='readonly')
        entry.pack(padx=24)
        tk.Button(root, text='完成 / 跳过', command=root.destroy).pack(pady=18)
        root.protocol('WM_DELETE_WINDOW', root.destroy)
        try:
            root.mainloop()
        finally:
            value.set('')
            try:
                root.destroy()
            except tk.TclError:
                pass

    def close(self):
        self._closed = True
        if self._server:
            self._server.shutdown()
        with self._condition:
            connections, handlers = list(self._connections), list(self._handlers)
        for connection in connections:
            connection.close(1001, 'Application stopped')
        for thread in handlers:
            thread.join(timeout=3)
        if self._thread:
            self._thread.join(timeout=3)
        with self._condition:
            self._sessions.clear()
            self._secret = ''
