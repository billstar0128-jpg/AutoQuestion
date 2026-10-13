"""Portable resource resolution and honest public download entry."""
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools')]
from autoquestion import __version__
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
            self.assertIn('AutoQuestion.exe', html)
            self.assertNotIn('<input', html)
            self.assertNotIn('@@VERSION@@', html)
            self.assertTrue((output / 'preview/index.html').is_file())
            self.assertFalse((output / 'windows').exists())


if __name__ == '__main__':
    unittest.main()
