"""Release candidate checks use public source files and synthetic data only."""
import ast
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'tools'))
from autoquestion import __version__
from autoquestion.cli import main, parse_args
from autoquestion.config import ConfigError
from autoquestion.provider_presets import PRESETS
from autoquestion.setup_wizard import Console
from autoquestion.startup import show_config
from autoquestion.user_config import UserConfigStore
from release_audit import audit, candidate_files, inspect_candidate
from test_setup import FakeCredentials, api_config


class ReleaseTests(unittest.TestCase):
    def test_public_candidate_audit_and_local_links(self):
        files, findings = audit(ROOT)
        self.assertTrue(files)
        self.assertEqual(findings, [])

    def test_version_cli_and_metadata_single_source(self):
        tree = ast.parse((ROOT / 'src/autoquestion/__init__.py').read_text(encoding='utf-8'))
        values = [ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                  and any(isinstance(target, ast.Name) and target.id == '__version__' for target in node.targets)]
        self.assertEqual(values, [__version__])
        metadata = (ROOT / 'pyproject.toml').read_text(encoding='utf-8')
        self.assertIn('attr = "autoquestion.__version__"', metadata)
        self.assertNotIn('version = "', metadata)
        for name in ('README.md', 'CHANGELOG.md', f'docs/RELEASE_NOTES_{__version__}.md'):
            self.assertIn(__version__, (ROOT / name).read_text(encoding='utf-8'))
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(['--version']), 0)
        self.assertEqual(output.getvalue().strip(), f'AutoQuestion {__version__}')

    def test_docs_match_preset_urls_and_existing_cli(self):
        readme = (ROOT / 'README.md').read_text(encoding='utf-8')
        for preset in PRESETS.values():
            if preset.default_base_url:
                with self.subTest(profile=preset.id):
                    self.assertIn(preset.default_base_url, readme)
        for flag in ('--setup', '--doctor', '--version', '--show-config', '--reset-config', '--open-demo'):
            with self.subTest(flag=flag):
                self.assertTrue(getattr(parse_args([flag]), flag[2:].replace('-', '_')))

    def test_inventory_never_reads_excluded_private_files_or_binary(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('.env', 'legacy_main.py', '.venv-win/private.txt', 'screenshots/private.png'):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'not-public')
            (root / 'README.md').write_text('# Test', encoding='utf-8')
            (root / 'unexpected.png').write_bytes(b'private-pixels')
            files, findings = candidate_files(root)
            self.assertEqual(files, [root / 'README.md'])
            self.assertEqual(len(findings), 1)
            self.assertNotIn('private-pixels', str(findings))
            self.assertEqual(findings[0].path, 'unexpected.png')

    def test_secret_and_invalid_encoding_findings_are_redacted(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'README.md'
            secret = 'sk-' + 'Q9abcXYZ' * 4
            path.write_text(secret, encoding='utf-8')
            findings = inspect_candidate(path, root)
            self.assertTrue(findings)
            self.assertNotIn(secret, str(findings))
            path.write_bytes(b'\xff\xfe')
            self.assertTrue(inspect_candidate(path, root))

    def test_show_config_rejects_query_secret_without_echo_or_vault_read(self):
        with TemporaryDirectory() as directory:
            store = UserConfigStore(Path(directory) / 'config.json')
            store.save(api_config())
            backend = FakeCredentials()
            output = []
            with self.assertRaises(ConfigError) as caught:
                show_config(parse_args(['--show-config']), store=store, backend=backend,
                            console=Console(output=output.append),
                            environ={'LLM_BASE_URL': 'https://example.invalid/v1?key=test-secret-value'})
            self.assertNotIn('test-secret-value', str(caught.exception) + str(output))
            self.assertEqual(backend.calls, [])


if __name__ == '__main__':
    unittest.main()
