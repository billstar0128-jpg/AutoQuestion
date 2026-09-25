"""Doctor：配置存在性、无秘密输出、无业务副作用、独立 CLI 与进程清理。"""
from collections.abc import Mapping
from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from autoquestion import __version__
from autoquestion.cli import main
from autoquestion.doctor import Check, ROOT, chromium_check, configuration_checks, project_checks, run_doctor
from autoquestion.secret_safety import inspect_text, scan_project


class NoSecretRead(Mapping):
    def __init__(self, values):
        self.values = values
    def __iter__(self):
        return iter(self.values)
    def __len__(self):
        return len(self.values)
    def __getitem__(self, key):
        if key == 'LLM_API_KEY':
            raise AssertionError('Doctor must never read secret values')
        return self.values[key]


def local_env():
    names = ('SYSTEMROOT', 'WINDIR', 'PATH', 'TEMP', 'TMP', 'USERPROFILE', 'LOCALAPPDATA', 'APPDATA')
    return {name: os.environ[name] for name in names if name in os.environ}


class DoctorTests(unittest.TestCase):
    def invoke(self, env, **kwargs):
        output = StringIO()
        with patch('autoquestion.doctor.dependency_check', side_effect=lambda d, m: Check('OK', d)), \
             patch('autoquestion.doctor.chromium_check', return_value=Check('OK', 'Chromium runtime')), \
             patch('autoquestion.doctor.user_configuration_checks', return_value=([], {}, False)), redirect_stdout(output):
            code = run_doctor(environ=env, root=ROOT, cwd=ROOT, **kwargs)
        return code, output.getvalue()

    def test_key_presence_does_not_read_value_and_can_pass(self):
        code, output = self.invoke(NoSecretRead({'LLM_API_KEY': object(), 'INPUT_MODE': 'demo'}))
        self.assertEqual(code, 0)
        self.assertIn('value not inspected', output)
        self.assertIn('Doctor result:\nPASS', output)

    def test_missing_key_warns_not_fails(self):
        code, output = self.invoke({'INPUT_MODE': 'demo', 'LLM_PROVIDER': 'fake'})
        self.assertEqual(code, 0)
        self.assertIn('[WARN] LLM_API_KEY', output)
        self.assertIn('Doctor result:\nWARNINGS', output)

    def test_provider_fields_reported_individually_without_values(self):
        checks = configuration_checks({'INPUT_MODE': 'auto', 'LLM_PROVIDER': 'openai'})
        output = '\n'.join(c.message for c in checks)
        for field in ('LLM_API_KEY', 'LLM_BASE_URL', 'LLM_MODEL'):
            self.assertIn(field, output)
        self.assertNotIn('FAIL', [c.level for c in checks])
        self.assertIn('Vision disabled', output)

    def test_invalid_public_values_safe_and_fail(self):
        for name in ('INPUT_MODE', 'HOTKEY', 'EXIT_KEY', 'IMAGE_MAX_EDGE', 'LLM_PROVIDER',
                     'LLM_TIMEOUT_SECONDS', 'LLM_SUPPORTS_VISION', 'LLM_BASE_URL'):
            with self.subTest(name=name):
                checks = configuration_checks({name: 'private-value'})
                self.assertIn('FAIL', [c.level for c in checks])
                self.assertNotIn('private-value', str(checks))

    def test_vision_semantics_fake_disabled_and_enabled(self):
        for env, expected in (({'INPUT_MODE': 'auto'}, 'Fake has no Vision'),
                              ({'INPUT_MODE': 'vision', 'LLM_PROVIDER': 'openai'}, 'Vision disabled'),
                              ({'INPUT_MODE': 'auto', 'LLM_PROVIDER': 'openai', 'LLM_SUPPORTS_VISION': 'true'}, 'Vision configured')):
            self.assertIn(expected, '\n'.join(c.message for c in configuration_checks(env)))

    def test_doctor_never_reads_env_or_calls_business_actions(self):
        original = Path.read_text
        def guarded(path, *args, **kwargs):
            self.assertNotEqual(path.name, '.env')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'read_text', guarded), \
             patch('autoquestion.config.load_env_file') as env_file, \
             patch('autoquestion.hotkeys.WindowsHotkeys') as hotkeys, \
             patch('autoquestion.capture.screen.ScreenCapture') as capture, \
             patch('autoquestion.llm.openai_compatible.OpenAI') as client:
            before = dict(os.environ)
            code, output = self.invoke({'INPUT_MODE': 'demo'}, env_file_requested=True)
            self.assertEqual(code, 0)
            self.assertIn('does not read --env-file', output)
            self.assertEqual(dict(os.environ), before)
            for action in (env_file, hotkeys, capture, client):
                action.assert_not_called()

    def test_legacy_environment_and_missing_project_are_visible(self):
        with TemporaryDirectory() as directory, patch('autoquestion.doctor.sys.prefix', 'D:/test/.venv'):
            code, output = self.invoke({'INPUT_MODE': 'demo'})
            self.assertEqual(code, 0)
            self.assertIn('not recommended .venv-win', output)
            checks = project_checks(Path(directory), Path(directory))
            self.assertIn('FAIL', [c.level for c in checks])

    def test_missing_dependency_does_not_dump_import_exception(self):
        from autoquestion.doctor import dependency_check
        with patch('autoquestion.doctor.importlib.import_module', side_effect=ImportError('private-value')):
            result = dependency_check('pydantic', 'pydantic')
        self.assertEqual(result.level, 'FAIL')
        self.assertNotIn('private-value', result.message)

    def test_chromium_child_env_is_allowlisted_case_insensitively(self):
        env = NoSecretRead({'SystemRoot': 'C:/Windows', 'LLM_API_KEY': object(), 'INPUT_MODE': 'auto'})
        with patch('autoquestion.doctor.subprocess.run', return_value=Mock(returncode=0, stdout='{"ok":true}')) as run:
            self.assertEqual(chromium_check(env).level, 'OK')
        child_env = run.call_args.kwargs['env']
        self.assertEqual(child_env['SYSTEMROOT'], 'C:/Windows')
        self.assertNotIn('LLM_API_KEY', child_env)
        self.assertNotIn('INPUT_MODE', child_env)
        self.assertEqual(child_env['PLAYWRIGHT_BROWSERS_PATH'], '0')

    def test_chromium_timeout_or_failure_is_sanitized(self):
        for failure in (subprocess.TimeoutExpired('private-value', 25), OSError('private-value')):
            with self.subTest(error=type(failure)), patch('autoquestion.doctor.subprocess.run', side_effect=failure):
                result = chromium_check({})
                self.assertEqual(result.level, 'FAIL')
                self.assertNotIn('private-value', result.message)

    def test_cli_doctor_precedes_env_loading_and_application_import(self):
        with patch('autoquestion.doctor.run_doctor', return_value=0) as doctor, \
             patch('autoquestion.app.main') as app:
            self.assertEqual(main(['--doctor', '--env-file', 'not-read.env']), 0)
            doctor.assert_called_once_with(env_file_requested=True)
            app.assert_not_called()

    def test_probe_close_failure_cannot_report_success(self):
        from autoquestion.doctor_browser import main as probe
        output = StringIO()
        with patch('autoquestion.doctor_browser.contain_process_tree', return_value=1), \
             patch('playwright.sync_api.sync_playwright') as factory, redirect_stdout(output):
            playwright = factory.return_value.__enter__.return_value
            playwright.chromium.executable_path = str(ROOT / 'main.py')
            browser = playwright.chromium.launch.return_value
            browser.new_context.return_value.new_page.return_value.evaluate.return_value = 'complete'
            browser.close.side_effect = RuntimeError('private-value')
            self.assertEqual(probe(), 1)
            factory.return_value.__exit__.assert_called_once()
        self.assertEqual(json.loads(output.getvalue()), {'ok': False})
        self.assertNotIn('private-value', output.getvalue())


class SecretSafetyTests(unittest.TestCase):
    def test_detects_literals_without_disclosing_them(self):
        token = 'sk-' + 'aBc01234' * 4
        bearer = 'Bearer ' + 'Z9' * 20
        cookie_value = 'session=' + 'X8' * 15
        values = {'API_KEY': token, 'Authorization': bearer, 'Cookie': cookie_value}
        text = '\n'.join(f'{name} = {json.dumps(value)}' for name, value in values.items())
        findings = inspect_text(text, 'example.py')
        self.assertGreaterEqual(len(findings), 3)
        self.assertNotIn(token, str(findings))
        self.assertNotIn('session=', str(findings))

    def test_mock_credentials_and_hotkeys_are_not_secrets(self):
        text = 'LLM_API_KEY=test-api-key\nHOTKEY=F8\nEXIT_KEY=ESC\nAPI_KEY="mock-token"\nLLM_API_KEY=<your-key>'
        self.assertEqual(inspect_text(text, '.env.example', example=True), [])

    def test_example_nonplaceholder_rejected_even_short(self):
        findings = inspect_text('LLM_API_KEY=abc', '.env.example', example=True)
        self.assertEqual(findings[0].line, 1)
        self.assertNotIn('abc', str(findings))

    def test_scan_excludes_private_files_and_virtualenv(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            secret = 'sk-' + 'qWe12345' * 4
            for path in (root/'.env', root/'legacy_main.py', root/'.venv-win'/'secret.py'):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(secret)
            (root/'main.py').write_text('API_KEY="test-api-key"')
            self.assertEqual(scan_project(root), [])
            (root/'.env.example').write_text('LLM_API_KEY=' + secret)
            self.assertTrue(scan_project(root))


@unittest.skipUnless(sys.platform == 'win32', 'Windows runtime / hotkeys')
class DoctorProcessTests(unittest.TestCase):
    @unittest.skipIf(os.environ.get('AUTOQUESTION_CI') == '1', 'Local held-hotkey test')
    def test_real_doctor_version_no_env_no_hotkey_leak(self):
        from autoquestion.config import Config
        from autoquestion.hotkeys import WindowsHotkeys
        env = local_env() | {'INPUT_MODE': 'demo', 'LLM_PROVIDER': 'fake', 'PYTHONIOENCODING': 'utf-8'}
        with TemporaryDirectory() as directory, WindowsHotkeys(Config()):
            env['APPDATA'] = directory
            # 测试持有 F8/ESC，Doctor 若尝试注册便会失败。
            fixture = Path(directory)/'.env'
            content = 'LLM_API_KEY=test-api-key\nINPUT_MODE=invalid\n'
            fixture.write_text(content)
            result = subprocess.run([sys.executable, str(ROOT/'main.py'), '--doctor', '--env-file', str(fixture)],
                                    cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8', timeout=35)
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn('Chromium runtime: isolated headless launch / close passed', result.stdout)
            self.assertIn('WARNINGS', result.stdout)
            self.assertNotIn('test-api-key', result.stdout + result.stderr)
            self.assertNotIn('Triggered', result.stdout)
            self.assertEqual(fixture.read_text(), content)
            self.assertEqual(list(Path(directory).iterdir()), [fixture])
        with WindowsHotkeys(Config()):
            pass
        version = subprocess.run([sys.executable, str(ROOT/'main.py'), '--version'], cwd=ROOT, env=env,
                                 capture_output=True, text=True, timeout=5)
        self.assertEqual(version.stdout.strip(), f'AutoQuestion {__version__}')

    def test_doctor_and_version_work_without_site_packages(self):
        env = local_env() | {'PYTHONIOENCODING': 'utf-8', 'INPUT_MODE': 'demo'}
        version = subprocess.run([sys.executable, '-S', str(ROOT/'main.py'), '--version'], cwd=ROOT, env=env,
                                 capture_output=True, text=True, encoding='utf-8', timeout=5)
        self.assertEqual(version.returncode, 0)
        result = subprocess.run([sys.executable, '-S', str(ROOT/'main.py'), '--doctor'], cwd=ROOT, env=env,
                                capture_output=True, text=True, encoding='utf-8', timeout=35)
        self.assertEqual(result.returncode, 1)
        self.assertIn('[FAIL] pydantic unavailable', result.stdout)
        self.assertNotIn('Traceback', result.stdout + result.stderr)
