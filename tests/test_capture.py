"""所有像素均由测试生成；绝不读取真实桌面或真实 .env。"""
from contextlib import nullcontext
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
import ctypes
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from PIL import Image
from autoquestion.capture.screen import (
    CapturedImage, CaptureError, ScreenCapture, WindowTarget, WindowsWindowAPI,
)


def synthetic_image(width=32, height=16):
    with Image.new('RGB', (width, height), 'white') as image, BytesIO() as buffer:
        image.save(buffer, format='PNG')
        return CapturedImage(buffer.getvalue(), width, height)


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.target = WindowTarget(123, 456, -100, 50, 3100, 1650)
        self.api = Mock()
        self.api.physical_coordinates.side_effect = lambda: nullcontext()
        self.api.foreground.return_value = self.target.hwnd
        self.api.describe.return_value = self.target
        self.patch_api = patch('autoquestion.capture.screen.WindowsWindowAPI', return_value=self.api)
        self.patch_api.start()
        self.addCleanup(self.patch_api.stop)
        self.capture = ScreenCapture()

    def test_target_snapshot_contains_original_handle_and_bounds(self):
        self.assertEqual(self.capture.snapshot_target(), self.target)
        self.api.describe.assert_called_once_with(123)

    def test_snapshot_failure_is_safe(self):
        self.api.describe.side_effect = OSError('private-value')
        with self.assertRaises(CaptureError) as error:
            self.capture.snapshot_target()
        self.assertNotIn('private-value', str(error.exception))

    def test_window_change_during_snapshot(self):
        self.api.foreground.side_effect = [123, 999]
        with self.assertRaises(CaptureError):
            self.capture.snapshot_target()

    def test_capture_returns_in_memory_png_resized_proportionally(self):
        grabber = Mock()
        grabber.monitors = [dict(left=-1920, top=0, width=6000, height=2160)]
        grabber.grab.return_value = SimpleNamespace(size=(3200, 1600), rgb=b'\xff' * (3200 * 1600 * 3))
        with patch('autoquestion.capture.screen.mss.MSS') as factory:
            factory.return_value.__enter__.return_value = grabber
            with patch('builtins.open', side_effect=AssertionError('Disk writes forbidden')):
                image = self.capture.capture(self.target)
        self.assertIsInstance(image, CapturedImage)
        self.assertEqual((image.width, image.height), (2048, 1024))
        grabber.grab.assert_called_once_with(self.target.region)
        factory.return_value.__exit__.assert_called_once()
        with Image.open(BytesIO(image.data)) as png:
            self.assertEqual(png.size, (2048, 1024))
            self.assertEqual(png.format, 'PNG')
        self.assertNotIn(str(image.data), repr(image))

    def test_small_images_not_upscaled(self):
        target = WindowTarget(123, 456, 0, 0, 1, 1)
        self.api.describe.return_value = target
        grabber = Mock(monitors=[dict(left=0, top=0, width=1920, height=1080)])
        grabber.grab.return_value = SimpleNamespace(size=(1, 1), rgb=b'\xff' * 3)
        with patch('autoquestion.capture.screen.mss.MSS') as factory:
            factory.return_value.__enter__.return_value = grabber
            image = self.capture.capture(target)
        self.assertEqual((image.width, image.height), (1, 1))

    def test_png_encoding_failure_closes_mss_and_hides_details(self):
        target = WindowTarget(123, 456, 0, 0, 1, 1)
        self.api.describe.return_value = target
        grabber = Mock(monitors=[dict(left=0, top=0, width=1920, height=1080)])
        grabber.grab.return_value = SimpleNamespace(size=(1, 1), rgb=b'\xff' * 3)
        with patch('autoquestion.capture.screen.mss.MSS') as factory, patch.object(Image.Image, 'save', side_effect=OSError('PRIVATE_PNG')):
            factory.return_value.__enter__.return_value = grabber
            with self.assertRaises(CaptureError) as caught:
                self.capture.capture(target)
            factory.return_value.__exit__.assert_called_once()
        self.assertNotIn('PRIVATE_PNG', str(caught.exception))

    def test_changed_or_moved_window_is_rejected_before_grab(self):
        for changed in (replace(self.target, hwnd=999), replace(self.target, left=1),
                        replace(self.target, process_id=999)):
            self.api.describe.return_value = changed
            with self.subTest(changed=changed), patch('autoquestion.capture.screen.mss.MSS') as factory:
                with self.assertRaises(CaptureError):
                    self.capture.capture(self.target)
                factory.assert_not_called()

    def test_window_change_after_grab_discards_pixels(self):
        self.api.foreground.side_effect = [123, 999]
        grabber = Mock(monitors=[dict(left=-1920, top=0, width=6000, height=2160)])
        with patch('autoquestion.capture.screen.mss.MSS') as factory:
            factory.return_value.__enter__.return_value = grabber
            with self.assertRaises(CaptureError):
                self.capture.capture(self.target)
        grabber.grab.assert_called_once()

    def test_offscreen_and_oversized_windows_rejected(self):
        grabber = Mock(monitors=[dict(left=0, top=0, width=1920, height=1080)])
        with patch('autoquestion.capture.screen.mss.MSS') as factory:
            factory.return_value.__enter__.return_value = grabber
            with self.assertRaises(CaptureError):
                self.capture.capture(self.target)
            grabber.grab.assert_not_called()
        huge = replace(self.target, right=20000, bottom=20000)
        self.api.describe.return_value = huge
        with patch('autoquestion.capture.screen.mss.MSS') as factory:
            with self.assertRaises(CaptureError):
                self.capture.capture(huge)
            factory.assert_not_called()

    def test_backend_error_does_not_leak_details(self):
        with patch('autoquestion.capture.screen.mss.MSS', side_effect=RuntimeError('private-value')):
            with self.assertRaises(CaptureError) as error:
                self.capture.capture(self.target)
        self.assertNotIn('private-value', str(error.exception))

    def test_image_and_size_constraints(self):
        for args in ((b'private-value', 1, 1), (b'\x89PNG\r\n\x1a\n', 0, 1),
                     (b'\x89PNG\r\n\x1a\n', 4097, 1)):
            with self.subTest(args=args), self.assertRaises(CaptureError):
                CapturedImage(*args)
        with self.assertRaises(CaptureError):
            ScreenCapture(512)


class WindowsBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.api = WindowsWindowAPI.__new__(WindowsWindowAPI)
        self.api.user32 = Mock()
        self.api.dwmapi = Mock()

    def test_dpi_restored_even_on_error(self):
        self.api.user32.SetThreadDpiAwarenessContext.side_effect = [1234, 1]
        with self.assertRaises(RuntimeError):
            with self.api.physical_coordinates():
                raise RuntimeError('test')
        calls = self.api.user32.SetThreadDpiAwarenessContext.call_args_list
        self.assertEqual(calls[0].args[0].value, ctypes.c_void_p(-4).value)
        self.assertEqual(calls[1].args, (1234,))

    def test_dpi_failure_is_explicit(self):
        self.api.user32.SetThreadDpiAwarenessContext.return_value = 0
        with self.assertRaises(CaptureError):
            with self.api.physical_coordinates():
                self.fail('DPI failure must prevent capture')

    def test_no_foreground_and_minimized_window(self):
        with self.assertRaises(CaptureError):
            self.api.describe(0)
        self.api.user32.IsIconic.return_value = True
        with self.assertRaises(CaptureError):
            self.api.describe(123)

    def test_dwm_bounds_and_getwindowrect_fallback(self):
        self.api.user32.IsIconic.return_value = False
        def process(hwnd, pointer):
            pointer._obj.value = 456
            return 1
        self.api.user32.GetWindowThreadProcessId.side_effect = process
        def rectangle(pointer):
            pointer._obj.left, pointer._obj.top = -100, 50
            pointer._obj.right, pointer._obj.bottom = 900, 550
        def dwm(hwnd, attribute, pointer, size):
            rectangle(pointer)
            return 0
        self.api.dwmapi.DwmGetWindowAttribute.side_effect = dwm
        self.assertEqual(self.api.describe(123), WindowTarget(123, 456, -100, 50, 900, 550))
        self.api.user32.GetWindowRect.assert_not_called()
        self.api.dwmapi.DwmGetWindowAttribute.side_effect = None
        self.api.dwmapi.DwmGetWindowAttribute.return_value = -1
        self.api.user32.GetWindowRect.side_effect = lambda hwnd, pointer: rectangle(pointer) or 1
        self.assertEqual(self.api.describe(123).left, -100)
        self.api.user32.GetWindowRect.assert_called_once()


if __name__ == '__main__':
    unittest.main()
