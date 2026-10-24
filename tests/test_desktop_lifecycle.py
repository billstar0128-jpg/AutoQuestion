"""Cross-process activation and native-window shutdown boundaries."""
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests')]
from autoquestion.desktop_app import main
from autoquestion.desktop_instance import DesktopInstance
from autoquestion.user_config import UserConfigStore
from autoquestion.web_ui import UIController, UIError, UIServer
from test_setup import FakeCredentials
from test_web_ui import simulated_app
from test_core import wait_until


class Event:
    def __init__(self):
        self.callbacks = []
    def __iadd__(self, callback):
        self.callbacks.append(callback)
        return self
    def emit(self):
        for callback in self.callbacks:
            callback()


class Window:
    native = None
    def __init__(self):
        from types import SimpleNamespace
        self.events = SimpleNamespace(closing=Event(), closed=Event())
    def destroy(self):
        self.events.closing.emit()
        self.events.closed.emit()


@unittest.skipUnless(sys.platform == 'win32', 'Windows desktop instance')
class DesktopLifecycleTests(unittest.TestCase):
    def test_default_renderer_import_initializes_updater_without_network(self):
        """Exercise the production default import branch; passing a renderer skips it."""
        with TemporaryDirectory() as directory:
            store = UserConfigStore(Path(directory) / 'config.json')
            controller = UIController(store=store, backend=FakeCredentials(), run_app=simulated_app)
            updater = Mock()
            updater.snapshot.return_value = {'status': 'idle', 'current': '0.5.0'}
            window, test = Window(), self
            class Webview:
                def create_window(self, title, url, **kwargs):
                    return window
                def start(self, **kwargs):
                    test.assertIs(controller.updater, updater)
                    test.assertEqual(controller.state()['update']['status'], 'idle')
                    window.destroy()
            with patch.dict(sys.modules, {'webview': Webview()}), \
                 patch('autoquestion.updates.UpdateManager', return_value=updater) as factory, \
                 patch('autoquestion.updates.ReleaseClient.open', side_effect=AssertionError('Unexpected network')) as network:
                self.assertEqual(main(store=store, controller=controller), 0)
            factory.assert_called_once_with()
            network.assert_not_called()
            updater.close.assert_called()
            self.assertTrue(controller.closing)
            self.assertFalse(store.path.exists())

    def child(self, profile, script):
        code = 'import sys; sys.path.insert(0, sys.argv[1]); from autoquestion.desktop_instance import DesktopInstance; ' + script
        return subprocess.run([sys.executable, '-c', code, str(ROOT / 'src'), str(profile)],
                              check=True, capture_output=True, text=True, timeout=12,
                              creationflags=subprocess.CREATE_NO_WINDOW).stdout.strip()

    def test_other_process_reopens_then_lock_is_released(self):
        with TemporaryDirectory() as directory:
            profile = Path(directory) / 'config.json'
            activated = threading.Event()
            with DesktopInstance(profile) as first:
                self.assertTrue(first.primary)
                first.activate(activated.set)
                self.assertEqual(self.child(profile, 'with_instance = DesktopInstance(sys.argv[2]); with_instance.__enter__(); print(with_instance.primary, with_instance.reopen()); with_instance.close()'), 'False True')
                self.assertTrue(activated.wait(3))
            self.assertFalse(first.thread.is_alive())
            self.assertEqual(self.child(profile, 'instance = DesktopInstance(sys.argv[2]); instance.__enter__(); print(instance.primary); instance.close()'), 'True')

    def test_crashed_owner_can_be_replaced_without_deleting_state(self):
        with TemporaryDirectory() as directory:
            profile = Path(directory) / 'config.json'
            profile.write_text('preserved settings', encoding='utf-8')
            code = ('import sys; sys.path.insert(0, sys.argv[1]); from autoquestion.desktop_instance import DesktopInstance; '
                    'instance=DesktopInstance(sys.argv[2]); instance.__enter__(); print(instance.primary, flush=True); sys.stdin.read()')
            child = subprocess.Popen([sys.executable, '-c', code, str(ROOT / 'src'), str(profile)],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                self.assertEqual(child.stdout.readline().strip(), 'True')
                with DesktopInstance(profile) as contender:
                    self.assertFalse(contender.primary)
                    child.terminate()  # Only the fixture process we just created.
                    child.wait(5)
                    with DesktopInstance(profile) as recovered:
                        self.assertTrue(recovered.primary)
                self.assertEqual(profile.read_text(), 'preserved settings')
            finally:
                if child.poll() is None:
                    child.terminate()
                    child.wait(5)
                child.stdin.close()
                child.stdout.close()

    def test_native_close_stops_worker_http_and_rejects_new_start(self):
        with TemporaryDirectory() as directory:
            store = UserConfigStore(Path(directory) / 'config.json')
            controller = UIController(store=store, backend=FakeCredentials(), run_app=simulated_app)
            window = Window()
            test = self
            servers = []
            def server_factory(value):
                server = UIServer(value)
                servers.append(server)
                return server
            class Webview:
                def create_window(self, title, url, **kwargs):
                    return window
                def start(self, **kwargs):
                    controller.start({'offline_demo': True})
                    wait_until(lambda: controller.state()['active'] and controller.runner is not None)
                    window.destroy()
                    with test.assertRaises(UIError):
                        controller.start({'offline_demo': True})
            with patch('autoquestion.desktop_app.UIServer', side_effect=server_factory):
                self.assertEqual(main(store=store, controller=controller, webview_module=Webview()), 0)
            self.assertTrue(controller.closing)
            self.assertFalse(controller.thread.is_alive())
            self.assertEqual(controller.history, [])
            self.assertEqual(servers[0].socket.fileno(), -1)
            self.assertFalse(store.path.exists())
