"""Non-secret display preferences survive private WebView profiles without touching API config."""
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from autoquestion.ui_preferences import UIPreferences


class UIPreferencesTests(unittest.TestCase):
    def test_absent_file_defaults_without_creating_configuration(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'ui-preferences.json'
            self.assertEqual(UIPreferences(path).load(), {'theme': 'system'})
            self.assertFalse(path.exists())

    def test_theme_survives_new_instance_and_model_config_is_untouched(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'ui-preferences.json'
            config = path.with_name('config.json'); config.write_text('synthetic existing model config')
            self.assertEqual(UIPreferences(path).save({'theme': 'dark'}), {'theme': 'dark'})
            self.assertEqual(UIPreferences(path).load(), {'theme': 'dark'})
            self.assertEqual(json.loads(path.read_text()), {'theme': 'dark'})
            self.assertEqual(config.read_text(), 'synthetic existing model config')

    def test_invalid_input_and_failed_replace_preserve_previous_choice(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'ui-preferences.json'; preferences = UIPreferences(path)
            preferences.save({'theme': 'light'})
            for data in ({'theme': True}, {'theme': 'red'}, {'theme': 'dark', 'api_key': 'test-only'}, [], {}):
                with self.subTest(data=data), self.assertRaises(ValueError): preferences.save(data)
            with patch('autoquestion.ui_preferences.os.replace', side_effect=OSError('synthetic error')):
                with self.assertRaises(OSError): preferences.save({'theme': 'dark'})
            self.assertEqual(preferences.load(), {'theme': 'light'})
            self.assertEqual([p.name for p in Path(directory).iterdir()], ['ui-preferences.json'])

    def test_corrupt_or_oversized_preference_uses_default_without_startup_failure(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'ui-preferences.json'
            for payload in ('{', '[]', '{"theme":"dark","theme":"light"}', '{"theme":"dark","unknown":1}', 'x' * 4097):
                with self.subTest(size=len(payload)):
                    path.write_text(payload)
                    self.assertEqual(UIPreferences(path).load(), {'theme': 'system'})
