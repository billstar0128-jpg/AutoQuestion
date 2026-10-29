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
                    until(lambda: window.evaluate_js("document.querySelector('#provider').options.length === 5 && !document.querySelector('#api-key').disabled"))
                    assert window.evaluate_js("document.querySelector('#demo-button') === null")
                    window.evaluate_js("document.querySelector('#model').value='deepseek-flash'; document.querySelector('#vision').checked=true; document.querySelector('#api-key').value='test-native-window-key'; document.querySelector('#save-button').click();")
                    stage = 'native configuration and secure save'
                    until(lambda: store.path.exists())
                    saved = store.load()
                    identifier = saved.credential_id
                    assert identifier and WindowsCredentials().exists(identifier)
                    assert 'test-native-window-key' not in store.path.read_text()
                    until(lambda: window.evaluate_js("!document.querySelector('#view-workspace').hidden"))
                    assert window.evaluate_js("document.querySelector('#api-key').value === ''")
                    until(lambda: controller.state()['window']['available'])
                    stage = 'native light and dark preferences'
                    for theme in ('dark', 'light'):
                        until(lambda: window.evaluate_js('!pending'))
                        window.evaluate_js("document.querySelector('#theme-select').value=" + json.dumps(theme)
                                           + "; document.querySelector('#theme-select').dispatchEvent(new Event('change', {bubbles:true}));")
                        until(lambda: controller.state()['preferences']['theme'] == theme)
                        until(lambda: window.evaluate_js('document.documentElement.dataset.theme === ' + json.dumps(theme)))
                        assert json.loads(controller.preferences.path.read_text(encoding='utf-8')) == {'theme': theme}
                        from .ui_preferences import UIPreferences
                        assert UIPreferences(controller.preferences.path).load() == {'theme': theme}
                    # Exercise the explicit test-only Fake path; the real UI must not regain a Demo invitation.
                    controller.start({'offline_demo': True})
                    stage = 'real native F8 Fake answer'
                    until(lambda: native and controller.state()['status'] == 'READY')
                    post = ctypes.WinDLL('user32', use_last_error=True).PostThreadMessageW
                    post.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
                    post.restype = wintypes.BOOL
                    assert post(controller.thread.native_id, WM_HOTKEY, native[-1].analyze_id, 0)
                    until(lambda: controller.state()['history'] and controller.state()['status'] == 'READY')
                    assert controller.state()['history'][0]['answer']['selected_text'] == '巴黎'
                    until(lambda: window.evaluate_js("document.querySelector('#answer-text').textContent.includes('巴黎')"))
                    record = controller.state()['history'][0]
                    displayed = window.evaluate_js("Object.fromEntries(['question-text','answer-text','answer-reason'].map(id => [id, document.getElementById(id).textContent]))")
                    assert displayed['question-text'] == record['question']['question_text']
                    assert displayed['answer-reason'] == record['answer']['short_reason']
                    assert displayed['answer-reason']
                    stage = 'native 80 square and answer restoration'
                    original_bounds = controller.window.backend.geometry()
                    until(lambda: window.evaluate_js('!pending'))
                    window.evaluate_js("document.querySelector('#compact-button').click()")
                    until(lambda: controller.state()['window']['mode'] == 'compact')
                    until(lambda: window.evaluate_js("document.body.classList.contains('native-compact')"))
                    assert controller.window.backend.geometry()[2:] == (80, 80)
                    assert window.evaluate_js("!document.querySelector('#compact-expand').hidden && document.querySelector('#normal-shell').hidden")
                    until(lambda: window.evaluate_js('!pending'))
                    window.evaluate_js("document.querySelector('#compact-expand').click()")
                    until(lambda: controller.state()['window']['mode'] == 'normal')
                    until(lambda: window.evaluate_js("!document.body.classList.contains('native-compact') && !document.querySelector('#view-workspace').hidden"))
                    assert controller.window.backend.geometry() == original_bounds
                    assert displayed == window.evaluate_js("Object.fromEntries(['question-text','answer-text','answer-reason'].map(id => [id, document.getElementById(id).textContent]))")
                    assert window.evaluate_js("!document.querySelector('#copy-answer').disabled")
                    # Check actual DOM selection without reading or overwriting the user's system clipboard.
                    for field, text in displayed.items():
                        selection = window.evaluate_js("(() => { const element=document.getElementById(" + json.dumps(field)
                                                       + "); if(getComputedStyle(element).userSelect==='none') return null;"
                                                       + "const range=document.createRange();range.selectNodeContents(element);"
                                                       + "const selected=getSelection();selected.removeAllRanges();selected.addRange(range);return selected.toString(); })()")
                        assert selection == text
                    window.evaluate_js('getSelection().removeAllRanges()')
                    stage = 'second process activates existing window'
                    until(lambda: window.evaluate_js('!pending'))
                    window.evaluate_js("document.querySelector('#compact-button').click()")
                    until(lambda: controller.state()['window']['mode'] == 'compact')
                    env = dict(os.environ, APPDATA=str(profile))
                    command = [sys.executable] if getattr(sys, 'frozen', False) else [sys.executable, str(Path(__file__).resolve().parents[2] / 'tools/desktop_entry.py')]
                    duplicate = subprocess.run(command, env=env, cwd=directory, timeout=15,
                                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                               creationflags=subprocess.CREATE_NO_WINDOW)
                    assert duplicate.returncode == 0
                    until(lambda: controller.state()['window']['mode'] == 'normal')
                    until(lambda: window.evaluate_js("!document.body.classList.contains('native-compact')"))
                    assert displayed == window.evaluate_js("Object.fromEntries(['question-text','answer-text','answer-reason'].map(id => [id, document.getElementById(id).textContent]))")
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
                                  'light and dark preferences persist through the authenticated UI',
                                  'own F8 message / test-only Fake answer', 'native 80x80 compact and geometry restoration',
                                  'question, answer and reason preserved and selectable; copy action remains available',
                                  'duplicate process expands and reuses window',
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
