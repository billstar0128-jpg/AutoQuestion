"""Real loopback transport with synthetic peer identities; native identity tested separately."""
from dataclasses import replace
import json
import logging
import os
from pathlib import Path
import socket
import sys
import threading
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from websockets.sync.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus
from autoquestion.browser_bridge import BrowserBridge
from autoquestion.browser_identity import BrowserClassifier, ProcessIdentity, browser_peer, process_identity, tcp_owner
from autoquestion.capture.browser import BrowserExtractionError
from autoquestion.capture.screen import CaptureError, WindowTarget

ORIGIN = 'chrome-extension://' + 'a' * 32
CHROME = ProcessIdentity(42, r'c:\browser\chrome.exe', 10)
EDGE = ProcessIdentity(43, r'c:\browser\msedge.exe', 11)


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.resolver = Mock(return_value=CHROME)
        self.bridge = BrowserBridge(port=0, resolver=self.resolver, timeout=.15)
        self.bridge.start()
        self.addCleanup(self.bridge.close)
        self.target = WindowTarget(100, 42, 0, 0, 800, 600, executable=CHROME.image, process_started=10)

    def client(self, token=None):
        client = connect(f'ws://127.0.0.1:{self.bridge.port}/bridge', origin=ORIGIN, proxy=None)
        self.addCleanup(client.close)
        client.send(json.dumps(dict(v=1, type='hello', token=token or self.bridge._secret)))
        return client

    def ready(self):
        client = self.client()
        self.assertEqual(json.loads(client.recv())['type'], 'ready')
        client.send(json.dumps(dict(v=1, type='state', epoch=1, window=2, tab=3)))
        with self.bridge._condition:
            self.assertTrue(self.bridge._condition.wait_for(lambda: self.bridge.pin(self.target) is not None, 2))
        return client

    def test_roundtrip_and_no_secret_logging(self):
        client = self.ready()
        verify = Mock()
        results = []
        worker = threading.Thread(target=lambda: results.append(self.bridge.extract_for_target(
            self.target, verify, self.bridge.pin(self.target))))
        with self.assertLogs('autoquestion', level=logging.DEBUG) as logs:
            worker.start()
            request = json.loads(client.recv(timeout=2))
            self.assertEqual((request['window'], request['tab']), (2, 3))
            client.send(json.dumps(dict(v=1, type='result', request=request['request'], status='ok',
                                       question=dict(kind='radio', stem='Synthetic?', options=['Yes', 'No']))))
            worker.join(2)
        self.assertNotIn(self.bridge._secret, '\n'.join(logs.output))
        self.assertNotIn('Synthetic?', '\n'.join(logs.output))
        self.assertFalse(worker.is_alive())
        self.assertEqual(results[0].question_type.value, 'true_false')
        self.assertEqual(verify.call_count, 2)

    def test_invalid_token_and_invalid_origin(self):
        with self.assertRaises(ConnectionClosed):
            self.client('x' * 32).recv(timeout=2)
        for origin in ('https://example.invalid', 'null', None):
            with self.subTest(origin=origin), self.assertRaises(InvalidStatus):
                connect(f'ws://127.0.0.1:{self.bridge.port}/bridge', origin=origin, proxy=None)
        self.assertIsNone(self.bridge.pin(self.target))

    def test_paths_and_query_tokens_rejected(self):
        for path in ('/', '/bridge?token=synthetic'):
            with self.subTest(path=path), self.assertRaises(InvalidStatus):
                connect(f'ws://127.0.0.1:{self.bridge.port}{path}', origin=ORIGIN, proxy=None)

    def test_two_browsers_process_birth_and_ambiguity(self):
        self.ready()
        self.resolver.return_value = EDGE
        edge = self.client()
        edge.recv(timeout=2)
        edge.send(json.dumps(dict(v=1, type='state', epoch=1, window=4, tab=5)))
        target = replace(self.target, process_id=43, executable=EDGE.image, process_started=11)
        with self.bridge._condition:
            self.assertTrue(self.bridge._condition.wait_for(lambda: self.bridge.pin(target) is not None, 2))
        self.assertNotEqual(self.bridge.pin(target).session, self.bridge.pin(self.target).session)
        self.assertIsNone(self.bridge.pin(replace(target, process_started=12)))
        self.resolver.return_value = CHROME
        duplicate = self.client(); duplicate.recv(timeout=2)
        duplicate.send(json.dumps(dict(v=1, type='state', epoch=1, window=2, tab=3)))
        with self.bridge._condition:
            self.assertTrue(self.bridge._condition.wait_for(lambda: self.bridge.pin(self.target) is None, 2))

    def test_timeout_disconnect_reconnect_and_changed_state(self):
        client = self.ready()
        pin = self.bridge.pin(self.target)
        with self.assertRaises(BrowserExtractionError):
            self.bridge.extract_for_target(self.target, Mock(), pin)
        client.send(json.dumps(dict(v=1, type='state', epoch=2, window=2, tab=4)))
        with self.bridge._condition:
            self.bridge._condition.wait_for(lambda: pin.session.state[0] == 2, 2)
        with self.assertRaises(CaptureError):
            self.bridge.extract_for_target(self.target, Mock(), pin)
        client.close()
        with self.bridge._condition:
            self.bridge._condition.wait_for(lambda: not pin.session.alive, 2)
        self.assertIsNone(self.bridge.pin(self.target))
        self.ready()
        self.assertIsNotNone(self.bridge.pin(self.target))

    def test_malformed_oversized_and_unsolicited_question_close(self):
        for raw in ('{', 'x' * 65537, json.dumps(dict(v=1, type='result', request='a'*32, status='unavailable'))):
            with self.subTest(length=len(raw)):
                client = self.ready()
                client.send(raw)
                with self.assertRaises(ConnectionClosed):
                    client.recv(timeout=2)
                client.close()

    def test_close_clears_secret_socket_and_threads(self):
        client = self.ready()
        thread = self.bridge._thread
        self.bridge.close()
        self.assertFalse(thread.is_alive())
        self.assertFalse(self.bridge._sessions)
        self.assertEqual(self.bridge._secret, '')
        with self.assertRaises(ConnectionClosed):
            client.recv(timeout=2)

    def test_lost_session_cannot_verify_fallback_tab(self):
        client = self.ready()
        pin = self.bridge.pin(self.target)
        client.close()
        with self.bridge._condition:
            self.assertTrue(self.bridge._condition.wait_for(lambda: not pin.session.alive, 2))
        with self.assertRaises(CaptureError):
            self.bridge.verify_pin(pin)


class NativeIdentityTests(unittest.TestCase):
    def test_classifier_only_executable_basename(self):
        for name, expected in [(r'C:\Chrome\CHROME.EXE', 'Chrome'), ('msedge.exe', 'Edge'),
                               ('chrome.exe.txt', None), ('wps.exe', None), ('', None), ('notepad.exe', None)]:
            self.assertEqual(BrowserClassifier.classify(name), expected)

    @unittest.skipUnless(sys.platform == 'win32', 'Windows API')
    def test_real_own_process_and_loopback_owner(self):
        identity = process_identity(os.getpid())
        self.assertEqual(identity.pid, os.getpid())
        self.assertGreater(identity.born, 0)
        with socket.socket() as server, socket.socket() as client:
            server.bind(('127.0.0.1', 0)); server.listen()
            client.connect(server.getsockname())
            incoming, _ = server.accept()
            with incoming:
                self.assertEqual(tcp_owner(client.getsockname()[1], server.getsockname()[1]), os.getpid())

    def test_network_child_and_reused_parent_pid(self):
        child = ProcessIdentity(44, CHROME.image, 20)
        with patch('autoquestion.browser_identity.tcp_owner', return_value=44), \
             patch('autoquestion.browser_identity._parents', return_value={44: 42, 42: 1}), \
             patch('autoquestion.browser_identity.process_identity', side_effect=[child, CHROME, OSError()]):
            self.assertEqual(browser_peer(1, 2), CHROME)
        with patch('autoquestion.browser_identity.tcp_owner', return_value=44), \
             patch('autoquestion.browser_identity._parents', return_value={44: 42}), \
             patch('autoquestion.browser_identity.process_identity', side_effect=[child, replace(CHROME, born=30)]):
            self.assertEqual(browser_peer(1, 2), child)
