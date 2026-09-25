"""Release startup policy, real headless navigation and isolated mock Setup."""
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
import sys
import threading
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from autoquestion.app import main, Status
from autoquestion.browser_session import BrowserSession
from autoquestion.capture.screen import ScreenCapture, WindowTarget
from autoquestion.cli import parse_args
from autoquestion.config import Config
from autoquestion.schemas import VisionAnalysisResult
from autoquestion.setup_wizard import Console
from autoquestion.startup import resolve_startup
from autoquestion.user_config import UserConfigStore
from test_capture import synthetic_image
from test_idle_navigation import NavigationProbe
from test_setup import FakeCredentials, SECRET
from test_vision import vision_payload
from pydantic import SecretStr


class StartupUXTests(unittest.TestCase):
    def setUp(self):
        self.capture = Mock(spec=ScreenCapture)
        self.capture.snapshot_target.return_value = WindowTarget(123, 456, 0, 0, 900, 700)
        self.capture.capture.return_value = synthetic_image()
        self.provider = Mock(supports_vision=True)
        self.provider.analyze_image.return_value = VisionAnalysisResult.model_validate(vision_payload())

    def trigger(self, runner):
        runner._clock = lambda: 100 + runner.trigger_count
        self.assertTrue(runner.trigger())
        runner._worker.join(10)
        self.assertFalse(runner._worker.is_alive())
        self.assertEqual(runner.state, Status.READY)

    def run_app(self, config, args=(), listen=None, runtime=None):
        observed = []
        def listening(runner):
            self.assertEqual(runner.state, Status.READY)
            observed.append(runner)
            if listen:
                listen(runner)
            runner.stop()
        with patch('autoquestion.app.load_config', return_value=config), \
             patch('autoquestion.hotkeys.WindowsHotkeys') as hotkeys, \
             patch('autoquestion.router.ScreenCapture', return_value=self.capture), \
             patch('autoquestion.router.vision_provider', return_value=self.provider), \
             patch('autoquestion.vision.ScreenCapture', return_value=self.capture), \
             patch('autoquestion.vision.vision_provider', return_value=self.provider), \
             self.assertLogs('autoquestion', 'INFO') as logs:
            hotkeys.return_value.__enter__.return_value.listen.side_effect = listening
            code = main(list(args), runtime=runtime)
        if observed:
            hotkeys.return_value.__exit__.assert_called_once()
            self.assertEqual(observed[0].state, Status.STOPPED)
        self.assertFalse(any(t.name in {'autoquestion-worker', 'autoquestion-browser'} for t in threading.enumerate()))
        return code, '\n'.join(logs.output)

    def test_auto_without_browser_ready_vision_no_child_process_or_browser_thread(self):
        # Do not mock BrowserSession: a regression that starts any child fails here.
        with patch('subprocess.Popen', side_effect=AssertionError('Unexpected child process')) as spawn:
            code, output = self.run_app(Config(input_mode='auto', llm_provider='openai'), listen=self.trigger)
            spawn.assert_not_called()
        self.assertEqual(code, 0)
        self.assertIn('Fallback: VISION', output)
        self.capture.capture.assert_called_once_with(self.capture.snapshot_target.return_value)
        self.provider.analyze_image.assert_called_once()

    def test_vision_and_fixed_demo_start_without_browser(self):
        for mode in ('vision', 'demo'):
            with self.subTest(mode=mode), patch('subprocess.Popen') as spawn:
                code, output = self.run_app(Config(input_mode=mode), listen=self.trigger)
                spawn.assert_not_called()
                self.assertEqual(code, 0)
                self.assertIn('答案：A', output)

    def test_open_demo_conflicts_with_management_commands(self):
        for command in ('--doctor', '--version', '--setup', '--show-config', '--reset-config'):
            with self.subTest(command=command), redirect_stderr(StringIO()), self.assertRaises(SystemExit) as error:
                parse_args(['--open-demo', command])
            self.assertEqual(error.exception.code, 2)

    def test_fixed_demo_rejects_open_demo_before_browser_or_hotkeys(self):
        with patch('autoquestion.browser_session.BrowserSession') as browser:
            code, output = self.run_app(Config(input_mode='demo'), ['--open-demo'])
        self.assertEqual(code, 1)
        self.assertIn('INPUT_MODE=demo', output)
        browser.assert_not_called()

    def test_auto_open_demo_real_dom_canvas_back_and_cleanup(self):
        browser = BrowserSession(headless=True)
        self.addCleanup(browser.close)
        def listen(runner):
            self.capture.snapshot_target.return_value = WindowTarget(123, browser._process_id, 0, 0, 900, 700)
            probe = NavigationProbe(browser)
            self.trigger(runner)
            self.capture.capture.assert_not_called()
            self.assertTrue(probe.click_while_idle('打开 Canvas 测试题'))
            self.assertEqual(probe.payload['bands'], [True] * 5)
            self.trigger(runner)
            self.assertTrue(probe.click_while_idle('返回 DOM 测试题'))
            self.trigger(runner)
            self.assertEqual(browser._call(lambda: browser._adapter.page.locator('input:checked').count()), 0)
        with patch('autoquestion.browser_session.BrowserSession', return_value=browser), \
             patch('autoquestion.browser_session.WindowsWindowAPI') as windows:
            windows.return_value.browser_windows.return_value = [123]
            code, output = self.run_app(Config(input_mode='auto'), ['--open-demo'], listen)
        self.assertEqual(code, 0)
        self.assertEqual(output.count('Input: DOM\n'), 2)
        self.assertEqual(output.count('Fallback: VISION'), 1)
        self.provider.analyze_image.assert_called_once()
        self.assertTrue(browser._closed)
        self.assertFalse(browser._thread.is_alive())
        self.assertFalse(browser._browser.is_connected())

    def test_dom_automatically_opens_and_vision_explicit_demo_never_extracts(self):
        for mode, flags in (('dom', ()), ('dom', ('--open-demo',)), ('vision', ('--open-demo',))):
            with self.subTest(mode=mode, flags=flags):
                browser = BrowserSession(headless=True)
                self.addCleanup(browser.close)
                with patch('autoquestion.browser_session.BrowserSession', return_value=browser), \
                     patch.object(browser, 'extract_for_target', side_effect=AssertionError('No AUTO route')):
                    code, output = self.run_app(Config(input_mode=mode), flags, self.trigger)
                self.assertEqual(code, 0)
                self.assertTrue(browser._closed)
                self.assertIn('答案：A', output)
                if mode == 'vision':
                    self.assertIn('Vision mode will not use DOM', output)

    def test_interrupt_releases_optional_browser_and_no_browser_paths(self):
        def interrupted(runner):
            self.trigger(runner)
            raise KeyboardInterrupt()
        for flags in ((), ('--open-demo',)):
            with self.subTest(flags=flags):
                browser = BrowserSession(headless=True) if flags else None
                if browser:
                    self.addCleanup(browser.close)
                with patch('autoquestion.browser_session.BrowserSession', return_value=browser) as factory:
                    code, _ = self.run_app(Config(input_mode='auto'), flags, interrupted)
                self.assertEqual(code, 0)
                if browser:
                    self.assertTrue(browser._closed)
                else:
                    factory.assert_not_called()

    def test_first_run_optional_demo_default_no_yes_and_second_start(self):
        for answer in ('', 'y'):
            with self.subTest(answer=answer), TemporaryDirectory() as directory:
                store = UserConfigStore(Path(directory) / 'config.json')
                backend = FakeCredentials()
                outputs = []
                console = Console(input_fn=Mock(side_effect=['1', '', 'test-model', 'y', '1', '1', 'y', answer]),
                                  output=outputs.append, secret_fn=lambda: SecretStr(SECRET), interactive=True)
                runtime = resolve_startup(parse_args([]), store=store, backend=backend, console=console, environ={})
                self.assertEqual(runtime.open_demo, answer == 'y')
                self.assertNotIn('open_demo', store.path.read_text())
                self.assertNotIn(SECRET, store.path.read_text() + str(outputs) + repr(runtime))
                browser = BrowserSession(headless=True) if runtime.open_demo else None
                if browser:
                    self.addCleanup(browser.close)
                def listen(runner):
                    if browser:
                        self.capture.snapshot_target.return_value = WindowTarget(123, browser._process_id, 0, 0, 900, 700)
                    self.trigger(runner)
                from autoquestion.llm.fake import FakeLLMProvider
                with patch('autoquestion.browser_session.BrowserSession', return_value=browser) as factory, \
                     patch('autoquestion.browser_session.WindowsWindowAPI') as windows, \
                     patch('autoquestion.llm.openai_compatible.OpenAICompatibleProvider', return_value=FakeLLMProvider()):
                    windows.return_value.browser_windows.return_value = [123]
                    code, output = self.run_app(runtime.config, listen=listen, runtime=runtime)
                self.assertEqual(code, 0)
                self.assertIn('Input: DOM\n' if browser else 'Input: VISION', output)
                if not browser:
                    factory.assert_not_called()
                # A saved credential is reused; no Setup or open-demo question.
                next_console = Console(input_fn=Mock(side_effect=AssertionError('No Setup')), output=outputs.append,
                                       secret_fn=Mock(side_effect=AssertionError('No Key prompt')), interactive=True)
                second = resolve_startup(parse_args([]), store=store, backend=backend, console=next_console, environ={})
                self.assertFalse(second.open_demo)
                with patch('subprocess.Popen') as spawn:
                    self.assertEqual(self.run_app(second.config, runtime=second)[0], 0)
                    spawn.assert_not_called()

    def test_optional_demo_uses_effective_mode_after_environment_override(self):
        with TemporaryDirectory() as directory:
            store = UserConfigStore(Path(directory) / 'config.json')
            console = Console(input_fn=Mock(side_effect=['1', '', 'test-model', 'y', '1', '2', 'y']),
                              output=Mock(), secret_fn=lambda: SecretStr(SECRET), interactive=True)
            runtime = resolve_startup(parse_args(['--setup']), store=store, backend=FakeCredentials(),
                                      console=console, environ={'INPUT_MODE': 'demo'})
            self.assertFalse(runtime.open_demo)
            self.assertEqual(runtime.config.input_mode, 'demo')
            self.assertEqual(store.load().input_mode, 'auto')


if __name__ == '__main__':
    unittest.main()
