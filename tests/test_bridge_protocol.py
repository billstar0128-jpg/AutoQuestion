"""Protocol contract, written before the bridge implementation. Synthetic data only."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from autoquestion.bridge_protocol import ProtocolError, decode_message, encode_message, VERSION


class ProtocolTests(unittest.TestCase):
    def test_valid_messages(self):
        for message in [
            dict(v=VERSION, type='hello', token='x' * 32),
            dict(v=VERSION, type='state', epoch=2, window=3, tab=4),
            dict(v=VERSION, type='state', epoch=3, window=-1, tab=-1),
            dict(v=VERSION, type='pong'),
            dict(v=VERSION, type='result', request='a' * 32, status='unavailable'),
            dict(v=VERSION, type='result', request='a' * 32, status='changed'),
            dict(v=VERSION, type='result', request='a' * 32, status='ok',
                 question=dict(kind='radio', stem='Synthetic question?', options=['Yes', 'No'])),
        ]:
            with self.subTest(kind=message['type']):
                self.assertEqual(decode_message(encode_message(message)), message)

    def test_reject_untrusted_or_unbounded_data_without_echo(self):
        private = 'synthetic-private-value'
        for raw in [b'{}', '[]', '{', '{"v":1,"v":1}', 'NaN',
                    json.dumps(dict(v=1, type='hello', token=private, extra=True)),
                    json.dumps(dict(v=1, type='hello', token=private)),
                    json.dumps(dict(v=2, type='pong')),
                    json.dumps(dict(v=1, type='state', epoch=True, window=1, tab=2)),
                    json.dumps(dict(v=1, type='result', request='a'*32, status='ok',
                                    question={'html': private})), 'x' * 65537]:
            with self.subTest(length=len(raw)):
                with self.assertRaises(ProtocolError) as raised:
                    decode_message(raw)
                self.assertNotIn(private, str(raised.exception))


if __name__ == '__main__':
    unittest.main()
