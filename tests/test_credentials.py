"""Mock Win32 ABI and console; never write the real credential vault."""
import ctypes
from ctypes import wintypes
from io import StringIO
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
import warnings

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from pydantic import SecretStr
from autoquestion.config import ConfigError
from autoquestion.credentials import Credential, CredentialError, Pointer, WindowsCredentials, new_identifier
from autoquestion.secret_input import masked_input, read_secret


class MaskedInputTests(unittest.TestCase):
    def enter(self, text):
        output = StringIO()
        value = masked_input(iter(text).__next__, output.write)
        return value, output.getvalue()

    def test_typing_paste_backspace_enter_and_unicode_never_echo(self):
        for text, expected in (('test-secret-value\r', 'test-secret-value'),
                               ('abc\b\bXY\r', 'aXY'), ('\b\r', ''),
                               ('密钥测试\r', '密钥测试'), ('x'*2048+'\r', 'x'*2048),
                               ('\x00Ksafe\xe0Msafe\r', 'safesafe')):
            with self.subTest(length=len(text)):
                value, output = self.enter(text)
                self.assertEqual(value.get_secret_value(), expected)
                self.assertTrue(set(output) <= set('*\b \n'))
                if expected:
                    self.assertNotIn(expected, repr(value))

    def test_cancel_eof_and_length_limit_clear_without_secret_output(self):
        for text, exception in (('secret\x03', KeyboardInterrupt), ('secret\x1a', EOFError), ('x'*4097, ConfigError)):
            with self.subTest(exception=exception):
                output = StringIO()
                with self.assertRaises(exception):
                    masked_input(iter(text).__next__, output.write)
                self.assertNotIn('secret', output.getvalue())
                self.assertTrue(output.getvalue().endswith('\n'))

    def test_getpass_warning_never_allows_echo_fallback(self):
        import getpass
        def unsafe(*args):
            warnings.warn('echo unavailable', getpass.GetPassWarning)
            self.fail('Warning should have been raised before echoing')
        with patch('autoquestion.secret_input.sys.platform', 'linux'), patch('getpass.getpass', side_effect=unsafe):
            with self.assertRaisesRegex(ConfigError, 'Windows Terminal'):
                read_secret()

    def test_getpass_safe_fallback_returns_secretstr(self):
        with patch('autoquestion.secret_input.sys.platform', 'linux'), patch('getpass.getpass', return_value='test-secret-value'):
            result = read_secret()
        self.assertNotIn('test-secret-value', repr(result))


@unittest.skipUnless(sys.platform == 'win32', 'Windows ABI')
class NativeCredentialTests(unittest.TestCase):
    def setUp(self):
        self.identifier = new_identifier('deepseek')
        self.api = Mock()
        self.backend = WindowsCredentials(api=self.api)

    def test_write_uses_generic_user_vault_and_zeros_native_buffer(self):
        observed = []
        def write(entry, flags):
            item = ctypes.cast(entry, Pointer).contents
            self.assertEqual((item.Type, item.Persist, item.TargetName), (1, 2, self.identifier))
            self.assertEqual(ctypes.string_at(item.CredentialBlob, item.CredentialBlobSize), b'test-secret-value')
            observed.append(item.CredentialBlobSize)
            return True
        self.api.CredWriteW.side_effect = write
        with patch('autoquestion.credentials.ctypes.memset', wraps=ctypes.memset) as wipe:
            self.backend.put(self.identifier, SecretStr('test-secret-value'))
            wipe.assert_called_once()
        self.assertEqual(observed, [17])

    def test_read_decodes_then_frees_native_buffer(self):
        buffer = ctypes.create_string_buffer(b'test-secret-value')
        item = Credential(Type=1, TargetName=self.identifier, CredentialBlobSize=17,
                          CredentialBlob=ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
        def read(name, kind, flags, out):
            ctypes.cast(out, ctypes.POINTER(Pointer))[0] = ctypes.pointer(item)
            return True
        self.api.CredReadW.side_effect = read
        value = self.backend.get(self.identifier)
        self.assertEqual(value.get_secret_value(), 'test-secret-value')
        self.assertNotIn('test-secret-value', repr(value))
        self.api.CredFree.assert_called_once()

    def test_metadata_enumeration_does_not_decode_secret_or_call_credread(self):
        item = Credential(Type=1, TargetName=self.identifier)
        other = Credential(Type=1, TargetName='OtherApp/account')
        array = (Pointer * 2)(ctypes.pointer(item), ctypes.pointer(other))
        def enumerate_ids(prefix, flags, count, out):
            self.assertEqual(prefix, 'AutoQuestion/*')
            ctypes.cast(count, ctypes.POINTER(wintypes.DWORD))[0] = 2
            ctypes.cast(out, ctypes.POINTER(ctypes.POINTER(Pointer)))[0] = ctypes.cast(array, ctypes.POINTER(Pointer))
            return True
        self.api.CredEnumerateW.side_effect = enumerate_ids
        with patch('autoquestion.credentials.ctypes.string_at', side_effect=AssertionError('No blob reads')):
            self.assertTrue(self.backend.exists(self.identifier))
        self.api.CredReadW.assert_not_called()
        self.api.CredFree.assert_called_once()

    def test_missing_and_native_failures_are_distinct_and_sanitized(self):
        self.api.CredReadW.return_value = False
        self.api.CredEnumerateW.return_value = False
        with patch('ctypes.get_last_error', return_value=1168):
            self.assertIsNone(self.backend.get(self.identifier))
            self.assertEqual(self.backend.list_ids(), ())
        self.api.CredWriteW.side_effect = OSError('test-secret-value')
        self.api.CredDeleteW.side_effect = OSError('test-secret-value')
        with patch('ctypes.get_last_error', return_value=5):
            for operation in (lambda: self.backend.get(self.identifier), self.backend.list_ids,
                              lambda: self.backend.put(self.identifier, SecretStr('test-secret-value')),
                              lambda: self.backend.delete(self.identifier)):
                with self.subTest(operation=operation), self.assertRaises(CredentialError) as caught:
                    operation()
                self.assertNotIn('test-secret-value', str(caught.exception))

    def test_foreign_identifiers_cannot_read_write_or_delete(self):
        for operation in (lambda: self.backend.get('OtherApp/account'),
                          lambda: self.backend.put('OtherApp/account', SecretStr('test-secret-value')),
                          lambda: self.backend.delete('OtherApp/account')):
            with self.assertRaises(CredentialError):
                operation()
        self.assertFalse(self.backend.exists('OtherApp/account'))
        self.assertEqual(self.api.mock_calls, [])


if __name__ == '__main__':
    unittest.main()
