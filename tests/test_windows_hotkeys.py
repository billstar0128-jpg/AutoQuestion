"""真实 Windows 注册和消息队列测试；不向用户桌面发送键盘输入。"""
import ctypes
import os
from ctypes import wintypes
from pathlib import Path
import sys
import threading
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from autoquestion.app import TaskRunner, Status, demo_callback
from autoquestion.config import Config
from autoquestion.hotkeys import WindowsHotkeys, HotkeyError, WM_HOTKEY
from test_core import wait_until


@unittest.skipUnless(sys.platform == 'win32', 'Windows only')
@unittest.skipIf(os.environ.get('AUTOQUESTION_CI') == '1', 'Local desktop hotkey test')
class NativeHotkeyTests(unittest.TestCase):
    def test_real_registration_five_messages_exit_and_reregister(self):
        completed = threading.Event()
        def callback(stop):
            demo_callback(stop)
            completed.set()
        runner = TaskRunner(callback)
        ready = threading.Event()
        errors = []
        ids = []
        def listen():
            try:
                with WindowsHotkeys(Config()) as hotkeys:
                    ids.extend([hotkeys.analyze_id, hotkeys.exit_id])
                    runner.ready()
                    ready.set()
                    hotkeys.listen(runner)
            except BaseException as exc:
                errors.append(exc)
                ready.set()
            finally:
                runner.close()
        listener = threading.Thread(target=listen, name='native-test-listener')
        listener.start()
        try:
            self.assertTrue(ready.wait(3))
            self.assertFalse(errors, 'Native registration failed; inspect local hotkey conflicts')
            time.sleep(0.2)
            self.assertTrue(listener.is_alive(), 'Listener exited without ESC')
            user32 = ctypes.WinDLL('user32', use_last_error=True)
            post = user32.PostThreadMessageW
            post.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
            post.restype = wintypes.BOOL
            for count in range(1, 6):
                completed.clear()
                self.assertTrue(post(listener.native_id, WM_HOTKEY, ids[0], 0))
                # 计数增加可能早于 WORKING 日志，不能误认上一轮的 READY。
                wait_until(lambda: completed.is_set() and runner.trigger_count == count
                           and runner.state == Status.READY)
                time.sleep(0.3)
            self.assertTrue(post(listener.native_id, WM_HOTKEY, ids[1], 0))
            listener.join(3)
            self.assertFalse(listener.is_alive())
            self.assertFalse(errors)
            self.assertEqual(runner.trigger_count, 5)
            with WindowsHotkeys(Config()):
                pass  # 重新注册证明旧热键已释放。
        finally:
            runner.stop()
            listener.join(3)

    def test_partial_registration_failure_releases_first_key(self):
        # 主线程先占 ESC；另一线程注册 F8 成功后，ESC 必须报错并释放 F8。
        errors = []
        with WindowsHotkeys(Config('F6', 'ESC')):
            def conflicting_registration():
                try:
                    with WindowsHotkeys(Config()):
                        pass
                except HotkeyError as exc:
                    errors.append(exc)
            thread = threading.Thread(target=conflicting_registration)
            thread.start()
            thread.join(3)
            self.assertFalse(thread.is_alive())
            self.assertEqual(len(errors), 1)
            self.assertIn('ESC', str(errors[0]))
            with WindowsHotkeys(Config('F8', 'F7')):
                pass


if __name__ == '__main__':
    unittest.main()
