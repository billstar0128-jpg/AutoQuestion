"""Portable resource resolution and honest public download entry."""
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools')]
from autoquestion import ANDROID_RELEASE_VERSION, __version__
from autoquestion.resources import resource_root
from build_web_preview import build


class DesktopDistributionTests(unittest.TestCase):
    def test_resource_root_source_and_frozen_are_independent_of_cwd(self):
        self.assertEqual(resource_root(), ROOT)
        with TemporaryDirectory() as directory, patch.object(sys, 'frozen', True, create=True), \
             patch.object(sys, '_MEIPASS', directory, create=True):
            self.assertEqual(resource_root(), Path(directory))

    def test_public_home_is_download_not_fake_configuration(self):
        with TemporaryDirectory() as directory:
            output = build(Path(directory))
            html = (output / 'index.html').read_text(encoding='utf-8')
            self.assertIn(f'AutoQuestion-{__version__}-Windows-x64.zip', html)
            self.assertIn(
                f'releases/download/v{ANDROID_RELEASE_VERSION}/AutoQuestion-{ANDROID_RELEASE_VERSION}-Android.apk',
                html,
            )
            self.assertIn('AutoQuestion.exe', html)
            self.assertNotIn('<input', html)
            self.assertNotIn('@@VERSION@@', html)
            self.assertTrue((output / 'preview/index.html').is_file())
            self.assertFalse((output / 'windows').exists())

    def test_windows_and_android_download_versions_are_independent(self):
        with TemporaryDirectory() as directory, \
             patch.multiple('build_web_preview', __version__='2.0.0', ANDROID_RELEASE_VERSION='1.3.1'):
            output = build(Path(directory))
            html = (output / 'index.html').read_text(encoding='utf-8')
            self.assertIn('releases/download/v2.0.0/AutoQuestion-2.0.0-Windows-x64.zip', html)
            self.assertIn('releases/download/v1.3.1/AutoQuestion-1.3.1-Android.apk', html)


if __name__ == '__main__':
    unittest.main()
