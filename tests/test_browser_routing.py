"""Normal browser and desktop route boundaries, using no real API or pixels."""
from dataclasses import replace
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from autoquestion.capture.browser import BrowserExtractionError
from autoquestion.capture.screen import CaptureError, WindowTarget
from autoquestion.llm.base import LLMProviderError
from autoquestion.llm.fake import demo_question
from autoquestion.router import InputRouter
from autoquestion.schemas import SourceType


class BrowserRoutingTests(unittest.TestCase):
    def setUp(self):
        self.capture, self.managed, self.bridge, self.answer, self.vision = (Mock() for _ in range(5))
        self.managed.owns_target.return_value = False
        self.target = WindowTarget(1, 2, 0, 0, 900, 700, executable=r'c:\browser\chrome.exe', process_started=3)
        self.capture.snapshot_target.return_value = self.target
        self.bridge.extract_for_target.return_value = demo_question().model_copy(update={'source_type': SourceType.DOM})
        self.router = InputRouter(self.capture, self.managed, self.answer, self.vision, Mock(), bridge=self.bridge)

    def run_job(self):
        self.router.prepare()(threading.Event())

    def test_browser_dom_zero_pixels_and_request_pinned_during_f8(self):
        callback = self.router.prepare()
        self.bridge.pin.assert_called_once_with(self.target)
        self.bridge.extract_for_target.assert_not_called()
        with self.assertLogs('autoquestion') as logs:
            callback(threading.Event())
        self.assertIn('Input: Browser DOM', '\n'.join(logs.output))
        self.answer.assert_called_once()
        self.capture.capture.assert_not_called()
        self.vision.for_target.assert_not_called()
        self.managed.extract_for_target.assert_not_called()

    def test_chrome_edge_unavailable_fallback_once(self):
        for executable in ('chrome.exe', 'msedge.exe'):
            self.capture.snapshot_target.return_value = replace(self.target, executable=executable)
            self.bridge.extract_for_target.side_effect = BrowserExtractionError('unavailable')
            self.vision.reset_mock()
            self.run_job()
            self.vision.for_target.assert_called_once_with(self.capture.snapshot_target.return_value)
            self.answer.assert_not_called()

    def test_desktop_direct_vision_no_extension_or_managed_read(self):
        for executable in ('wps.exe', 'notepad.exe', 'AcroRd32.exe', ''):
            with self.subTest(executable=executable), self.assertLogs('autoquestion') as logs:
                self.capture.snapshot_target.return_value = replace(self.target, executable=executable)
                self.run_job()
            self.assertNotIn('Fallback', '\n'.join(logs.output))
            self.bridge.pin.assert_not_called()
            self.bridge.extract_for_target.assert_not_called()
            self.managed.extract_for_target.assert_not_called()

    def test_provider_failure_after_dom_never_fallback(self):
        self.answer.side_effect = LLMProviderError('synthetic provider failure')
        with self.assertRaises(LLMProviderError):
            self.run_job()
        self.vision.for_target.assert_not_called()

    def test_target_or_tab_change_cancels_without_capture(self):
        self.bridge.extract_for_target.side_effect = CaptureError('target changed')
        with self.assertRaises(CaptureError):
            self.run_job()
        self.vision.for_target.assert_not_called()

    def test_strict_dom_no_fallback_for_desktop_or_browser(self):
        self.router.strict_dom = True
        for executable in ('notepad.exe', 'chrome.exe'):
            self.capture.snapshot_target.return_value = replace(self.target, executable=executable)
            self.bridge.extract_for_target.side_effect = BrowserExtractionError('unavailable')
            with self.assertRaises(BrowserExtractionError):
                self.run_job()
            self.vision.for_target.assert_not_called()

    def test_managed_session_has_priority_over_extension(self):
        self.managed.owns_target.return_value = True
        self.managed.extract_for_target.return_value = self.bridge.extract_for_target.return_value
        self.run_job()
        self.managed.extract_for_target.assert_called_once()
        self.bridge.extract_for_target.assert_not_called()
        self.bridge.pin.assert_not_called()
