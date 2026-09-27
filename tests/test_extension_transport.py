"""Load the real MV3 extension in an owned Chromium profile, not a personal browser.

This automation does not replace the separate Chrome / Edge Windows manual gates.
"""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import shutil
from tempfile import TemporaryDirectory
import threading
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from playwright.sync_api import sync_playwright
from autoquestion.browser_bridge import BrowserBridge
from autoquestion.capture.browser import BrowserExtractionError
from autoquestion.capture.screen import WindowTarget, CaptureError

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform == 'win32', 'Actual TCP process ownership requires Windows')
class ExtensionTransportTests(unittest.TestCase):
    def test_real_extension_origin_pair_process_match_and_on_demand_dom(self):
        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(ROOT / 'examples/browser_dom'), **kwargs)
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        bridge = BrowserBridge(timeout=2)
        os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', '0')
        try:
            bridge.start()
            with TemporaryDirectory() as profile, sync_playwright() as playwright:
                # Browser permission prompts are a manual gate. The automated harness adds
                # only its synthetic loopback host to a temporary copy of the manifest.
                # All executable JS is the exact shipped version, with no API mocks.
                extension_path = Path(profile) / 'test-extension'
                shutil.copytree(ROOT / 'extension', extension_path)
                manifest = json.loads((extension_path / 'manifest.json').read_text())
                manifest['host_permissions'] = ['http://127.0.0.1/*']
                (extension_path / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
                extension = str(extension_path)
                context = playwright.chromium.launch_persistent_context(profile, headless=True, channel='chromium',
                    args=[f'--disable-extensions-except={extension}', f'--load-extension={extension}'])
                try:
                    worker = context.service_workers[0] if context.service_workers else context.wait_for_event('serviceworker')
                    worker.evaluate("globalThis.testLoaded = false; chrome.tabs.onUpdated.addListener((id, change) => { if (change.status === 'complete') testLoaded = true; });")
                    worker.evaluate('(value) => { token = value; connect(); }', bridge._secret)
                    page = context.pages[0]
                    page.goto(f'http://127.0.0.1:{server.server_port}/single_choice.html')
                    page.bring_to_front()
                    worker.evaluate("() => testLoaded ? Promise.resolve() : new Promise(resolve => chrome.tabs.onUpdated.addListener((id, change) => { if (change.status === 'complete') resolve(); }))")
                    deadline = time.monotonic() + 5
                    while time.monotonic() < deadline:
                        revision = worker.evaluate('async () => { await refresh(); return epoch; }')
                        with bridge._condition:
                            if bridge._condition.wait_for(lambda: any(s.state and s.state[0] == revision and s.state[1] >= 0 for s in bridge._sessions), .2):
                                break
                    with bridge._condition:
                        self.assertEqual(len(bridge._sessions), 1, 'Real extension handshake/process validation failed')
                        identity = bridge._sessions[0].identity
                    cdp = context.browser.new_browser_cdp_session()
                    try:
                        processes = cdp.send('SystemInfo.getProcessInfo')['processInfo']
                        self.assertEqual(identity.pid, int(next(p['id'] for p in processes if p['type'] == 'browser')))
                    finally:
                        cdp.detach()
                    target = WindowTarget(1, identity.pid, 0, 0, 1200, 900,
                                          executable=identity.image, process_started=identity.born)
                    pin = bridge.pin(target)
                    self.assertIsNotNone(pin, 'Focused extension metadata missing')
                    question = bridge.extract_for_target(target, lambda: None, pin)
                    self.assertEqual(question.question_text, '法国的首都是哪里？')
                    self.assertEqual(len(question.options), 4)
                    self.assertEqual(page.locator(':checked').count(), 0)
                    self.assertFalse(bridge._sessions[0].request)
                    bridge.verify_pin(pin)
                    worker.evaluate('testLoaded = false')
                    page.goto(f'http://127.0.0.1:{server.server_port}/canvas_question.html')
                    worker.evaluate("() => testLoaded ? Promise.resolve() : new Promise(resolve => chrome.tabs.onUpdated.addListener((id, change) => { if (change.status === 'complete') resolve(); }))")
                    revision = worker.evaluate('async () => { await refresh(); return epoch; }')
                    with bridge._condition:
                        self.assertTrue(bridge._condition.wait_for(lambda: bridge._sessions[0].state[0] == revision, 2))
                    canvas_pin = bridge.pin(target)
                    with self.assertRaises(BrowserExtractionError):
                        bridge.extract_for_target(target, lambda: None, canvas_pin)
                    bridge.verify_pin(canvas_pin)  # Fallback can prove the original Canvas tab.
                    with self.assertRaises(CaptureError):
                        bridge.verify_pin(pin)  # The old DOM document identity is no longer valid.
                finally:
                    context.close()
        finally:
            bridge.close()
            server.shutdown(); server.server_close(); thread.join(2)
