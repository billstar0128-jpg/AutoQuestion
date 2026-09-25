"""运行：python -m unittest discover -s tests -v。"""
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from autoquestion.app import TaskRunner, Status
from autoquestion.config import Config, ConfigError, load_config


def wait_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError('Timed out waiting for expected state')


class ConfigTests(unittest.TestCase):
    def test_defaults_need_no_api_key(self):
        self.assertEqual(load_config({}), Config())

    def test_environment(self):
        self.assertEqual(load_config({'HOTKEY': ' f7 ', 'DEBOUNCE_MS': '300'}), Config('F7', 'ESC', 300))

    def test_invalid_config_does_not_echo_values(self):
        for values in ({'HOTKEY': 'private-value'}, {'DEBOUNCE_MS': 'private-value'},
                       {'DEBOUNCE_MS': '0'}, {'HOTKEY': 'ESC'}, {'HOTKEY': 'F12'}):
            with self.subTest(values=values):
                with self.assertRaises(ConfigError) as error:
                    load_config(values)
                self.assertNotIn('private-value', str(error.exception))


class RunnerTests(unittest.TestCase):
    def test_five_sequential_callbacks_and_debounce(self):
        now = [0.0]
        calls = []
        runner = TaskRunner(lambda stop: calls.append(1), clock=lambda: now[0])
        self.addCleanup(runner.close)
        for i in range(5):
            now[0] = i * 0.5
            self.assertTrue(runner.trigger())
            wait_until(lambda: runner.state == Status.READY)
            self.assertFalse(runner.trigger())
        self.assertEqual(len(calls), 5)
        self.assertEqual(runner.trigger_count, 5)
        self.assertFalse(runner.stop_event.is_set())

    def test_busy_rejects_concurrent_requests(self):
        entered = threading.Event()
        release = threading.Event()
        def callback(stop):
            entered.set()
            release.wait(2)
        runner = TaskRunner(callback)
        self.addCleanup(runner.close)
        self.addCleanup(release.set)
        self.assertTrue(runner.trigger())
        self.assertTrue(entered.wait(1))
        contenders = [threading.Thread(target=runner.trigger) for _ in range(20)]
        for thread in contenders:
            thread.start()
        for thread in contenders:
            thread.join()
        self.assertEqual(runner.trigger_count, 1)
        self.assertEqual(runner.state, Status.BUSY)
        release.set()
        wait_until(lambda: runner.state == Status.READY)

    def test_callback_error_recovers_without_leaking_exception(self):
        now = [0.0]
        calls = []
        def callback(stop):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError('private-value')
        runner = TaskRunner(callback, clock=lambda: now[0])
        self.addCleanup(runner.close)
        with self.assertLogs('autoquestion', level='INFO') as logs:
            runner.trigger()
            wait_until(lambda: runner.state == Status.READY)
        self.assertNotIn('private-value', '\n'.join(logs.output))
        self.assertIn('Status: ERROR', '\n'.join(logs.output))
        now[0] = 1.0
        self.assertTrue(runner.trigger())
        wait_until(lambda: runner.state == Status.READY)
        self.assertEqual(len(calls), 2)

    def test_exit_during_work_joins_worker(self):
        entered = threading.Event()
        def callback(stop):
            entered.set()
            stop.wait(2)
        runner = TaskRunner(callback)
        runner.trigger()
        self.assertTrue(entered.wait(1))
        runner.close()
        self.assertEqual(runner.state, Status.STOPPED)
        self.assertFalse(runner.trigger())
        self.assertFalse(any(t.name == 'autoquestion-worker' for t in threading.enumerate()))

    def test_worker_start_failure_recovers(self):
        runner = TaskRunner()
        self.addCleanup(runner.close)
        with patch('threading.Thread.start', side_effect=RuntimeError('private-value')):
            with self.assertLogs('autoquestion', level='ERROR'):
                self.assertFalse(runner.trigger())
        self.assertEqual(runner.state, Status.READY)


if __name__ == '__main__':
    unittest.main()
