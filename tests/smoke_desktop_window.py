"""Explicit interactive smoke: own synthetic WinForms target and WebView only.

Run with .venv-win/Scripts/python.exe tests/smoke_desktop_window.py.
No screenshots, credentials or question/answer history are written to disk.
"""
import ctypes
from ctypes import wintypes
from io import BytesIO
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time
from unittest.mock import patch

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'src'), str(Path(__file__).resolve().parent)]
from PIL import Image
import mss
from autoquestion.capture.screen import ScreenCapture, CapturedImage
from autoquestion.desktop_app import main
from autoquestion.user_config import UserConfigStore
from autoquestion.web_ui import UIController
from test_setup import FakeCredentials


def run():
    report = {'passed': False, 'private_screenshots': 0, 'paid_requests': 0, 'checks': []}
    with TemporaryDirectory(prefix='aq-native-window-') as directory:
        store = UserConfigStore(Path(directory) / 'config.json')
        controller = UIController(store=store, backend=FakeCredentials())
        def driver(window, controller, server):
            target_form = None
            try:
                assert window.events.loaded.wait(20), 'loaded event'
                deadline = time.monotonic() + 10
                while not controller.state()['window']['available']:
                    if time.monotonic() >= deadline:
                        raise AssertionError('native window binding')
                    time.sleep(0.02)
                owned = controller.window
                backend = owned.backend
                initial = backend.geometry()
                assert 320 <= initial[2] <= 460 and 360 <= initial[3] <= 700, initial
                controller.set_window_mode({'mode': 'compact'})
                assert backend.geometry()[2:] == (80, 80), backend.geometry()
                assert str(window.native.FormBorderStyle) == 'None', 'compact border'
                assert window.native.TopMost, 'compact topmost'
                # Real saved geometry, including a user resize/move.
                controller.set_window_mode({'mode': 'normal'})
                assert backend.geometry() == initial, ('restore bounds', backend.geometry(), initial)
                assert str(window.native.FormBorderStyle) == 'Sizable', 'normal border'
                assert not window.native.TopMost, 'normal topmost'
                report['checks'].append('normal small window / compact 80x80 borderless topmost / saved normal geometry')
                from System.Windows.Forms import FormWindowState
                backend._invoke(lambda: setattr(window.native, 'WindowState', FormWindowState.Minimized))
                assert not backend.hide_for_capture(), 'A minimized AQ must not be hidden/restored'
                assert window.native.WindowState == FormWindowState.Minimized
                backend._invoke(lambda: setattr(window.native, 'WindowState', FormWindowState.Normal))
                report['checks'].append('minimized workbench remains minimized during capture fallback')
                controller.set_window_mode({'mode': 'compact'})
                assert backend.geometry()[2:] == (80, 80), 'second compact'
                deadline = time.monotonic() + 5
                while not window.evaluate_js("!document.querySelector('#compact-box').hidden"):
                    if time.monotonic() >= deadline:
                        raise AssertionError('Compact native state did not reach the UI')
                    time.sleep(0.02)
                window.evaluate_js("document.querySelector('.compact-grip').dispatchEvent(new MouseEvent('mousedown', {bubbles:true, clientX:5, clientY:5})); window.dispatchEvent(new MouseEvent('mousemove', {bubbles:true, screenX:305, screenY:205})); window.dispatchEvent(new MouseEvent('mouseup', {bubbles:true}));")
                deadline = time.monotonic() + 5
                while backend.geometry()[:2] != (300, 200):
                    if time.monotonic() >= deadline:
                        raise AssertionError(('owned DOM drag did not move native frame', backend.geometry()))
                    time.sleep(0.02)
                window.evaluate_js("document.querySelector('#compact-expand').click()")
                deadline = time.monotonic() + 5
                while owned.mode != 'normal':
                    if time.monotonic() >= deadline:
                        raise AssertionError('AQ click did not expand native frame')
                    time.sleep(0.02)
                assert backend.geometry() == initial, ('AQ expand geometry', backend.geometry(), initial)
                report['checks'].append('native drag region moves only owned AQ; AQ click expands normal workspace')
                controller.set_window_mode({'mode': 'compact'})
                from System.Drawing import Color, Size, Point
                from System.Windows.Forms import Form, FormBorderStyle
                def create_target():
                    form = Form()
                    form.Text = 'AutoQuestion synthetic question — no user content'
                    form.BackColor = Color.Lime
                    form.TopMost = True
                    form.FormBorderStyle = getattr(FormBorderStyle, 'None')
                    form.Size = Size(600, 460)
                    form.Location = Point(120, 100)
                    form.Show()
                    form.Activate()
                    return form
                target_form = backend._invoke(create_target)
                question_hwnd = int(target_form.Handle.ToInt64())
                # Place AQ well inside the synthetic target; no other desktop pixel is read.
                backend.apply('compact', (180, 160, 80, 80))
                backend._invoke(target_form.Activate)
                user = backend.user
                user.SetForegroundWindow.argtypes = [wintypes.HWND]
                user.SetForegroundWindow.restype = wintypes.BOOL
                user.GetForegroundWindow.restype = wintypes.HWND
                backend._invoke(lambda: user.SetForegroundWindow(question_hwnd))
                foreground_available = user.GetForegroundWindow() == question_hwnd
                foreground_before = user.GetForegroundWindow()
                assert user.SetWindowPos(backend.hwnd, -1, 0, 0, 0, 0, 0x10 | 0x01 | 0x02)
                backend.dwm.DwmFlush()
                with owned.capture_scope():
                    capture = ScreenCapture()
                # When Windows refuses foreground activation, use only the explicit
                # synthetic HWND's rectangle. Do not bypass production focus checks.
                target = capture.snapshot_target() if foreground_available else capture._windows.describe(question_hwnd)
                assert target.hwnd == question_hwnd
                def capture_pixels():
                    if foreground_available:
                        return capture.capture(target)
                    with owned.capture_guard(target), mss.MSS() as grabber:
                        shot = grabber.grab(target.region)
                        with Image.frombytes('RGB', shot.size, shot.rgb) as pixels, BytesIO() as buffer:
                            pixels.save(buffer, format='PNG')
                            return CapturedImage(buffer.getvalue(), pixels.width, pixels.height)
                rect = wintypes.RECT()
                user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
                assert user.GetWindowRect(backend.hwnd, ctypes.byref(rect))
                point = ((rect.left + rect.right) // 2 - target.left,
                         (rect.top + rect.bottom) // 2 - target.top)
                user.SetWindowDisplayAffinity(backend.hwnd, 0)
                backend.dwm.DwmFlush()
                report['stage'] = 'MSS baseline capture of synthetic owned rectangle'
                with mss.MSS() as grabber:
                    shot = grabber.grab(target.region)
                    with Image.frombytes('RGB', shot.size, shot.rgb) as pixels:
                        assert pixels.getpixel(point) != (0, 255, 0), 'Fixture AQ must visibly overlap the target'
                supported = backend.exclude_from_capture()
                backend.dwm.DwmFlush()
                screenshot = capture_pixels()
                with Image.open(BytesIO(screenshot.data)) as pixels:
                    assert pixels.getpixel(point) == (0, 255, 0), 'AQ appeared in captured synthetic question'
                assert user.GetForegroundWindow() == foreground_before
                # Force the real hide/flush/noactivate fallback, even on supported Windows.
                user.SetWindowDisplayAffinity(backend.hwnd, 0)
                with patch.object(backend, 'exclude_from_capture', return_value=False):
                    screenshot = capture_pixels()
                with Image.open(BytesIO(screenshot.data)) as pixels:
                    assert pixels.getpixel(point) == (0, 255, 0), 'AQ fallback did not reveal the complete question'
                assert user.IsWindowVisible(backend.hwnd)
                assert user.GetForegroundWindow() == foreground_before
                report.update(passed=True, normal=list(initial[2:]), compact=[80, 80],
                              affinity_supported=supported, fallback_noactivate=True,
                              foreground_target_available=foreground_available,
                              saved_geometry_restored=True, images_written=0)
            except Exception as error:
                import traceback
                report.update(error=type(error).__name__, detail=str(error), traceback=traceback.format_exc())
            finally:
                if target_form is not None:
                    controller.window.backend._invoke(target_form.Close)
                window.destroy()
        main(store=store, controller=controller, test_driver=driver)
        assert controller.closing
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(run())
