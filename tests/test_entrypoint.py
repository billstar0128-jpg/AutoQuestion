"""在独立进程执行真实 main.py，用 WM_HOTKEY 消息完成入口验收。"""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import unittest
from tempfile import TemporaryDirectory


@unittest.skipUnless(sys.platform == 'win32', 'Windows only')
@unittest.skipIf(os.environ.get('AUTOQUESTION_CI') == '1', 'Local desktop hotkey test')
class EntrypointTests(unittest.TestCase):
    def test_main_stays_alive_five_triggers_then_exit(self):
        root = Path(__file__).resolve().parents[1]
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        env = dict(os.environ, PYTHONIOENCODING='utf-8', HOTKEY='F8', EXIT_KEY='ESC',
                   DEBOUNCE_MS='400', LLM_PROVIDER='fake', INPUT_MODE='demo', APPDATA=directory.name)
        bootstrap = "import threading,runpy; print(threading.get_native_id(),flush=True); runpy.run_path('main.py',run_name='__main__')"
        process = subprocess.Popen([sys.executable, '-u', '-c', bootstrap], cwd=root,
                                   env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, encoding='utf-8')
        lines = queue.Queue()
        output = []
        def read_output():
            for line in process.stdout:
                output.append(line)
                lines.put(line.strip())
        reader = threading.Thread(target=read_output)
        reader.start()
        def expect(expected):
            deadline = time.monotonic() + 4
            while time.monotonic() < deadline:
                line = lines.get(timeout=max(0.01, deadline-time.monotonic()))
                if line == expected:
                    return
            self.fail('Expected output missing')
        try:
            native_id = int(lines.get(timeout=4))
            expect('Status: READY')
            time.sleep(0.3)
            self.assertIsNone(process.poll())
            user32 = ctypes.WinDLL('user32', use_last_error=True)
            post = user32.PostThreadMessageW
            post.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
            post.restype = wintypes.BOOL
            for number in range(1, 6):
                self.assertTrue(post(native_id, 0x0312, 1, 0))
                expect(f'Triggered #{number}')
                expect('答案：A')
                expect('Status: READY')
                time.sleep(0.3)
            self.assertTrue(post(native_id, 0x0312, 2, 0))
            self.assertEqual(process.wait(timeout=4), 0)
            reader.join(2)
            text = ''.join(output)
            self.assertEqual(text.count('Triggered #'), 5)
            self.assertEqual(text.count('答案：A'), 5)
            self.assertEqual(text.count('99%'), 5)
            self.assertIn('FAKE (offline demo)', text)
            self.assertIn('Status: STOPPED', text)
            self.assertNotIn('Traceback', text)
            print('\nEntrypoint smoke output:\n' + text)
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=4)
            reader.join(2)
            process.stdout.close()


if __name__ == '__main__':
    unittest.main()
