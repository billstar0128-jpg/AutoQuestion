"""Explicit native EXE acceptance with a private profile and synthetic input only."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from . import __version__


def run(report_path):
    from .credentials import WindowsCredentials
    from .desktop_app import main
    from .hotkeys import WindowsHotkeys, WM_HOTKEY
    from .user_config import UserConfigStore
    from .web_ui import UIController
    result = dict(passed=False, version=__version__)
    stage = 'native launch'
    identifier = None
    original = WindowsHotkeys.listen
    native = []
    details = {}
    def listen(hotkeys, runner):
        native.append(hotkeys)
        original(hotkeys, runner)
    WindowsHotkeys.listen = listen
    try:
        with TemporaryDirectory(prefix='autoquestion-native-check-') as directory:
            profile = Path(directory) / 'Roaming'
            store = UserConfigStore(profile / 'AutoQuestion/config.json')
            controller = UIController(store=store)
            def driver(window, controller, server):
                nonlocal stage, identifier
                def until(predicate):
                    deadline = time.monotonic() + 20
                    while not predicate():
                        if time.monotonic() >= deadline:
                            raise RuntimeError('native check deadline')
                        time.sleep(0.05)
                try:
                    stage = 'native WebView2 first-run UI'
                    assert window.events.loaded.wait(20)
                    until(lambda: window.evaluate_js("document.querySelector('#provider').options.length === 6 && !document.querySelector('#api-key').disabled"))
                    window.evaluate_js("document.querySelector('#model').value='deepseek-flash'; document.querySelector('#vision').checked=true; document.querySelector('#api-key').value='test-native-window-key'; document.querySelector('#save-button').click();")
                    stage = 'native configuration and secure save'
                    until(lambda: store.path.exists())
                    saved = store.load()
                    identifier = saved.credential_id
                    assert identifier and WindowsCredentials().exists(identifier)
                    assert 'test-native-window-key' not in store.path.read_text()
                    until(lambda: window.evaluate_js("!document.querySelector('#view-workspace').hidden"))
                    assert window.evaluate_js("document.querySelector('#api-key').value === ''")
                    window.evaluate_js("document.querySelector('#demo-button').click()")
                    stage = 'real native F8 Fake answer'
                    until(lambda: native and controller.state()['status'] == 'READY')
                    post = ctypes.WinDLL('user32', use_last_error=True).PostThreadMessageW
                    post.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
                    post.restype = wintypes.BOOL
                    assert post(controller.thread.native_id, WM_HOTKEY, native[-1].analyze_id, 0)
                    until(lambda: controller.state()['history'] and controller.state()['status'] == 'READY')
                    assert controller.state()['history'][0]['answer']['selected_text'] == '巴黎'
                    until(lambda: window.evaluate_js("document.querySelector('#answer-text').textContent.includes('巴黎')"))
                    stage = 'second process activates existing window'
                    env = dict(os.environ, APPDATA=str(profile))
                    command = [sys.executable] if getattr(sys, 'frozen', False) else [sys.executable, str(Path(__file__).resolve().parents[2] / 'tools/desktop_entry.py')]
                    duplicate = subprocess.run(command, env=env, cwd=directory, timeout=15,
                                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                               creationflags=subprocess.CREATE_NO_WINDOW)
                    assert duplicate.returncode == 0
                    assert controller.state()['active'] and controller.state()['status'] == 'READY'
                    assert len(native) == 1
                    stage = 'native title-bar close'
                    details['port'] = server.server_port
                    hwnd = int(window.native.Handle.ToInt64())
                    user = ctypes.WinDLL('user32', use_last_error=True)
                    user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
                    assert user.PostMessageW(hwnd, 0x0010, 0, 0)
                    details['driver_passed'] = True
                except Exception as error:
                    details['error_type'] = type(error).__name__
                    details['driver_passed'] = False
                    window.destroy()
            assert main(store=store, controller=controller, test_driver=driver) == 0
            assert details.get('driver_passed')
            assert not controller.state()['active'] and not controller.history
            from .config import Config
            with WindowsHotkeys(Config()):
                pass
            try:
                connection = socket.create_connection(('127.0.0.1', details['port']), timeout=1)
            except OSError:
                pass
            else:
                connection.close()
                raise RuntimeError('HTTP server remained online')
            result = dict(passed=True, version=__version__,
                          checks=['native WebView2 window', 'first-run secure Key save',
                                  'own F8 message / Fake answer', 'duplicate process reuses window',
                                  'title-bar close exits GUI and HTTP service', 'F8 / ESC released'],
                          paid_requests=0, private_screenshots=0)
    except Exception as error:
        result.update(failed_stage=stage, error_type=details.get('error_type', type(error).__name__))
    finally:
        WindowsHotkeys.listen = original
        if identifier:
            WindowsCredentials().delete(identifier)
            assert not WindowsCredentials().exists(identifier)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if result['passed'] else 1
