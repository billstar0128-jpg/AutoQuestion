"""Native window mode and capture guards; all pixels and windows are fixtures."""
from contextlib import contextmanager
import http.client
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'src'), str(Path(__file__).resolve().parent)]
from autoquestion.web_ui import UIController, UIError, UIServer
from autoquestion.user_config import UserConfigStore
from test_setup import FakeCredentials


class WindowAPITests(unittest.TestCase):
    def test_http_only_controller_never_claims_native_window(self):
        with TemporaryDirectory() as directory:
            controller = UIController(store=UserConfigStore(Path(directory) / 'config.json'), backend=FakeCredentials())
            try:
                self.assertEqual(controller.state().get('window'), {'mode': 'normal', 'available': False})
                self.assertEqual(controller.set_window_mode({'mode': 'compact'}), {'mode': 'normal', 'available': False})
                for body in ({}, {'mode': 'fullscreen'}, {'mode': 'compact', 'path': 'ignored'}, {'mode': []}):
                    with self.subTest(body=body), self.assertRaises(UIError):
                        controller.set_window_mode(body)
            finally:
                controller.close()

    def test_window_api_requires_session_and_validates_body(self):
        from autoquestion.desktop_window import DesktopWindow
        with TemporaryDirectory() as directory:
            controller = UIController(store=UserConfigStore(Path(directory) / 'config.json'), backend=FakeCredentials())
            window = DesktopWindow(Backend())
            controller.bind_window(window)
            server = UIServer(controller)
            serving = threading.Thread(target=server.serve_forever, daemon=True)
            serving.start()
            def request(body, token=server.token):
                connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                connection.request('POST', '/api/window/mode', json.dumps(body),
                                   {'Origin': server.origin, 'Content-Type': 'application/json', 'X-AutoQuestion-Token': token})
                response = connection.getresponse()
                result = response.status, json.loads(response.read())
                connection.close()
                return result
            try:
                self.assertEqual(request({'mode': 'compact'}, token='invalid')[0], 403)
                self.assertEqual(window.snapshot()['mode'], 'normal')
                self.assertEqual(request({'mode': 'compact'}), (200, {'mode': 'compact', 'available': True}))
                self.assertEqual(controller.state()['window']['mode'], 'compact')
                self.assertEqual(request({'mode': 'normal', 'extra': 1})[0], 400)
                self.assertEqual(request({'mode': 'normal'})[0], 200)
            finally:
                controller.close()
                server.shutdown()
                server.close()
                serving.join(3)


class Backend:
    """A deterministic stand-in for unavailable WinForms, retaining geometry."""
    def __init__(self):
        self.bounds = (100, 200, 460, 600)
        self.affinity = False
        self.visible = True
        self.foreground = 99
        self.events = []
        self.hwnd = 55
    def geometry(self):
        return self.bounds
    def apply(self, mode, bounds):
        self.bounds = bounds
        self.events.append(('mode', mode, bounds))
    def exclude_from_capture(self):
        return self.affinity
    def hide_for_capture(self):
        shown = self.visible
        self.visible = False
        self.events.append('hide')
        return shown
    def restore_after_capture(self):
        self.visible = True
        self.events.append('show_noactivate')


class WindowModeTests(unittest.TestCase):
    def test_saved_normal_and_compact_coordinates_retain_their_own_monitor_dpi(self):
        from autoquestion.desktop_window import DesktopWindow, WindowBounds
        backend = Backend()
        backend.bounds = WindowBounds((100, 200, 440, 640), 1.5)
        window = DesktopWindow(backend)
        window.set_mode('compact')
        self.assertEqual(backend.bounds.scale, 1.5)
        backend.bounds = WindowBounds((700, 80, 80, 80), 2)
        window.set_mode('normal')
        self.assertEqual(backend.bounds, (100, 200, 440, 640))
        self.assertEqual(backend.bounds.scale, 1.5)
        window.set_mode('compact')
        self.assertEqual(backend.bounds, (700, 80, 80, 80))
        self.assertEqual(backend.bounds.scale, 2)

    def test_minimized_owned_window_is_not_restored_by_capture_fallback(self):
        from types import SimpleNamespace
        from autoquestion.desktop_window import WinFormsWindow
        backend = WinFormsWindow.__new__(WinFormsWindow)
        events = []
        backend.native = SimpleNamespace(Handle=SimpleNamespace(ToInt64=lambda: 55))
        import os
        def own_pid(hwnd, pointer):
            pointer._obj.value = os.getpid()
            return 1
        backend.user = SimpleNamespace(GetWindowThreadProcessId=own_pid, IsIconic=lambda hwnd: True,
                                       IsWindowVisible=lambda hwnd: True,
                                       SetWindowPos=lambda *args: events.append('hide') or True)
        backend.dwm = SimpleNamespace(DwmFlush=lambda: 0)
        self.assertFalse(backend.hide_for_capture())
        self.assertEqual(events, [])

    def test_geometry_uses_per_window_win32_dpi_when_winforms_device_dpi_is_stale(self):
        from types import SimpleNamespace
        import os
        from autoquestion.desktop_window import WinFormsWindow
        backend = WinFormsWindow.__new__(WinFormsWindow)
        backend.native = SimpleNamespace(InvokeRequired=False, DeviceDpi=96,
                                        Handle=SimpleNamespace(ToInt64=lambda: 55),
                                        Bounds=SimpleNamespace(X=150, Y=300, Width=660, Height=960))
        def own_pid(hwnd, pointer):
            pointer._obj.value = os.getpid()
            return 1
        backend.user = SimpleNamespace(GetWindowThreadProcessId=own_pid, GetDpiForWindow=lambda hwnd: 144)
        self.assertEqual(backend.geometry(), (100, 200, 440, 640))

    def test_compact_expand_restores_resized_geometry_and_remembers_dragged_compact(self):
        from autoquestion.desktop_window import DesktopWindow
        backend = Backend()
        window = DesktopWindow(backend)
        self.assertEqual(window.set_mode('compact'), {'mode': 'compact', 'available': True})
        self.assertEqual(backend.bounds, (100, 200, 80, 80))
        backend.bounds = (20, 30, 80, 80)  # User drags only the owned window.
        window.set_mode('normal')
        self.assertEqual(backend.bounds, (100, 200, 460, 600))
        backend.bounds = (300, 400, 390, 500)
        window.set_mode('compact')
        self.assertEqual(backend.bounds, (20, 30, 80, 80))
        window.set_mode('normal')
        self.assertEqual(backend.bounds, (300, 400, 390, 500))
        self.assertEqual(backend.foreground, 99)

    def test_capture_fallback_hides_only_owned_window_and_restores_on_error_without_focus(self):
        from autoquestion.desktop_window import DesktopWindow
        from autoquestion.capture.screen import WindowTarget
        backend = Backend()
        window = DesktopWindow(backend)
        target = WindowTarget(99, 7, 0, 0, 300, 400)
        with self.assertRaisesRegex(RuntimeError, 'synthetic'):
            with window.capture_guard(target):
                self.assertFalse(backend.visible)
                self.assertEqual(backend.foreground, target.hwnd)
                raise RuntimeError('synthetic capture error')
        self.assertTrue(backend.visible)
        self.assertEqual(backend.events, ['hide', 'show_noactivate'])
        self.assertEqual(backend.foreground, target.hwnd)
        backend.visible = False
        with window.capture_guard(target):
            pass
        self.assertFalse(backend.visible, 'An already hidden window must remain hidden')

    def test_affinity_excludes_without_hiding_and_self_capture_is_rejected(self):
        from autoquestion.desktop_window import DesktopWindow
        from autoquestion.capture.screen import CaptureError, WindowTarget
        backend = Backend()
        backend.affinity = True
        window = DesktopWindow(backend)
        with window.capture_guard(WindowTarget(99, 7, 0, 0, 300, 400)):
            self.assertTrue(backend.visible)
        self.assertEqual(backend.events, [])
        with self.assertRaises(CaptureError):
            with window.capture_guard(WindowTarget(55, 7, 0, 0, 300, 400)):
                self.fail('The application itself is not a question target')

    def test_capture_scope_is_native_thread_local_and_inherited_only_by_created_capture(self):
        from autoquestion.desktop_window import DesktopWindow
        from autoquestion.capture.screen import ScreenCapture
        window = DesktopWindow(Backend())
        with patch('autoquestion.capture.screen.WindowsWindowAPI'):
            before = ScreenCapture()
            with window.capture_scope():
                own = ScreenCapture()
                other = []
                thread = threading.Thread(target=lambda: other.append(ScreenCapture()))
                thread.start(); thread.join()
            after = ScreenCapture()
        self.assertIsNone(before.capture_guard)
        self.assertIsNotNone(own.capture_guard)
        self.assertIsNone(other[0].capture_guard)
        self.assertIsNone(after.capture_guard)

    def test_capture_pipeline_uses_guard_only_for_pixels_and_rejects_focus_change(self):
        from autoquestion.desktop_window import DesktopWindow
        from contextlib import nullcontext
        from types import SimpleNamespace
        from autoquestion.capture.screen import ScreenCapture, CaptureError, WindowTarget
        backend = Backend()
        window = DesktopWindow(backend)
        target = WindowTarget(99, 7, 0, 0, 10, 10)
        class API:
            physical_coordinates = lambda self: nullcontext()
            foreground = lambda self: backend.foreground
            describe = lambda self, hwnd: target
        class Grabber:
            monitors = [{'left': 0, 'top': 0, 'width': 100, 'height': 100}]
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def grab(self, region):
                assert not backend.visible, 'AQ must be excluded before any pixels are read'
                backend.foreground = 100  # A real user switch must still discard pixels.
                return SimpleNamespace(size=(10, 10), rgb=b'\xff' * 300)
        with patch('autoquestion.capture.screen.WindowsWindowAPI', API), window.capture_scope():
            capture = ScreenCapture()
        with patch('autoquestion.capture.screen.mss.MSS', Grabber):
            self.assertEqual(capture.snapshot_target(), target)
            self.assertEqual(backend.events, [], 'Metadata-only target acquisition must not hide windows')
            with self.assertRaises(CaptureError):
                capture.capture(target)
        self.assertTrue(backend.visible)
        self.assertEqual(backend.foreground, 100, 'Restoring AQ must not restore a previous foreground target')


if __name__ == '__main__':
    unittest.main()
