"""M14 field validation: offline, temporary config and fake credentials only."""
from contextlib import ExitStack, redirect_stdout, redirect_stderr
from io import StringIO
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from pydantic import SecretStr, ValidationError
from autoquestion.cli import main, parse_args
from autoquestion.config import (APISettingsError, load_llm_config, validate_base_url,
                                validate_model_id, validate_api_settings)
from autoquestion.setup_wizard import Console, SetupCancelled, run_setup
from autoquestion.startup import resolve_startup
from autoquestion.user_config import UserConfig, UserConfigError, UserConfigStore
from test_setup import FakeCredentials, api_config, SECRET


class SetupValidationTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = UserConfigStore(Path(self.directory.name) / 'config.json')
        self.backend = FakeCredentials()
        self.output, self.prompts = [], []
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        # No validation may perform HTTP or DNS, instantiate a model, or launch the app.
        for name in ('socket.socket.connect', 'socket.getaddrinfo',
                     'autoquestion.llm.openai_compatible.OpenAI'):
            self.stack.enter_context(patch(name, side_effect=AssertionError('Network forbidden')))

    def console(self, answers):
        items = iter(answers)
        def ask(prompt):
            self.prompts.append(prompt)
            result = next(items)
            if isinstance(result, BaseException):
                raise result
            return result
        return Console(input_fn=ask, output=self.output.append,
                       secret_fn=Mock(return_value=SecretStr(SECRET)), interactive=True)

    def test_url_structure_accepts_public_local_and_internal_endpoints(self):
        for url in ('https://api.deepseek.com', 'https://api.deepseek.com/v1',
                    'http://localhost:8000/v1', 'http://127.0.0.1:8000/v1',
                    'https://intranet/api', 'http://[::1]:1234/v2'):
            with self.subTest(url=url):
                self.assertEqual(validate_base_url('  ' + url + '  '), url)

    def test_url_invalid_structure_and_controls_never_echo(self):
        for url in ('deepseek-flash', 'model-name', 'gpt-xxx', 'glm-xxx',
                    'example.com', '', '   ', 'ftp://example.com', 'https://',
                    'https://example.com:bad', 'http://[broken', 'https://example.com/\x00',
                    '\nhttps://example.com', 'https://example.com\x85',
                    'https://test-secret-value@example.com', 'https://example.com?key=test-secret-value',
                    'https://example.com#test-secret-value'):
            with self.subTest(url=url), self.assertRaises(APISettingsError) as error:
                validate_base_url(url)
            self.assertNotIn(SECRET, str(error.exception))

    def test_model_accepts_reasonable_identifiers_and_trims(self):
        for model in ('deepseek-flash', 'provider/model-name', 'model.name', 'model-name_v2',
                      'namespace:model', 'provider/model@version', '模型-v2'):
            with self.subTest(model=model):
                self.assertEqual(validate_model_id('  ' + model + '  '), model)

    def test_model_rejects_urls_empty_and_controls(self):
        for model in ('https://api.deepseek.com', 'http://localhost:8000', 'HTTPS://example.com',
                      'custom://host/path', '', '   ', 'test\nmodel', '\tmodel', 'model\x7f', 'model\x85'):
            with self.subTest(model=model), self.assertRaises(APISettingsError):
                validate_model_id(model)

    def test_url_reprompt_precedes_model_and_preserves_provider(self):
        console = self.console(['1', 'deepseek-flash', 'model-name', 'example.com',
                                'https://api.deepseek.com', 'cancel'])
        with self.assertRaises(SetupCancelled):
            run_setup(self.store, self.backend, console)
        self.assertEqual(sum(p.startswith('API Base URL') for p in self.prompts), 4)
        self.assertEqual(sum(p.startswith('Selection') for p in self.prompts), 1)
        self.assertTrue(self.prompts[-1].startswith('Model ID'))
        self.assertEqual(sum('Invalid API Base URL' in s for s in self.output), 3)
        self.assertEqual(self.backend.calls, [])
        console.secret_fn.assert_not_called()
        self.assertFalse(self.store.path.exists())

    def test_model_reprompt_does_not_reask_url_or_reach_vision(self):
        console = self.console(['1', '', 'https://api.deepseek.com',
                                'http://localhost:8000', '   ', 'cancel'])
        with self.assertRaises(SetupCancelled):
            run_setup(self.store, self.backend, console)
        self.assertEqual(sum(p.startswith('API Base URL') for p in self.prompts), 1)
        self.assertEqual(sum(p.startswith('Model ID') for p in self.prompts), 4)
        self.assertFalse(any(p.startswith('Supports image') for p in self.prompts))
        self.assertEqual(self.backend.calls, [])
        console.secret_fn.assert_not_called()

    def test_every_preset_and_custom_can_override_url_after_correction(self):
        for index in range(1, 6):
            with self.subTest(profile=index):
                answers = [str(index)] + (['My gateway'] if index == 5 else [])
                answers += ['model-name', ' http://localhost:8000/v1 ', 'https://example.com',
                            ' provider/model@v2 ', 'y', '1', '2', 'y']
                result = run_setup(self.store, self.backend, self.console(answers))
                self.assertEqual(result.config.base_url, 'http://localhost:8000/v1')
                self.assertEqual(result.config.model, 'provider/model@v2')
                self.assertNotIn(SECRET, self.store.path.read_text(encoding='utf-8'))
                self.assertNotIn('put', self.backend.calls)

    def test_blank_uses_preset_but_custom_without_default_reprompts(self):
        result = run_setup(self.store, self.backend,
                           self.console(['1', '', 'test-model', 'y', '1', '2', 'y']))
        self.assertEqual(result.config.base_url, 'https://api.deepseek.com')
        self.prompts.clear()
        console = self.console(['5', '', '', 'http://127.0.0.1:8000/v1', 'cancel'])
        with self.assertRaises(SetupCancelled):
            run_setup(self.store, self.backend, console)
        self.assertEqual(sum(p.startswith('API Base URL') for p in self.prompts), 2)

    def test_first_run_and_explicit_setup_share_validation_then_reach_runtime(self):
        for flags in ([], ['--setup']):
            with self.subTest(flags=flags):
                self.store.reset()
                console = self.console(['1', 'model-name', 'https://api.deepseek.com',
                                        'https://example.com', 'test-model', 'y', '1', '2', 'y', ''])
                runtime = resolve_startup(parse_args(flags), store=self.store, backend=self.backend,
                                          console=console, environ={})
                self.assertEqual(runtime.config.llm_config.model, 'test-model')
                self.assertEqual(runtime.config.input_mode, 'auto')
                self.assertFalse(runtime.open_demo)

    def test_swapped_fields_detected_without_mutation_or_input_echo(self):
        values = {'LLM_API_KEY': SECRET, 'LLM_BASE_URL': 'deepseek-flash',
                  'LLM_MODEL': 'https://api.deepseek.com'}
        original = dict(values)
        with self.assertRaisesRegex(APISettingsError, 'appear to be reversed') as error:
            load_llm_config(values)
        self.assertEqual(values, original)
        self.assertNotIn(SECRET, str(error.exception))

    def test_saved_invalid_fields_and_unknown_provider_fail_before_credentials(self):
        for change, message in (({'base_url': 'model-name'}, 'Invalid API Base URL'),
                                ({'model': 'https://example.com'}, 'Invalid Model ID'),
                                ({'base_url': 'deepseek-flash', 'model': 'https://api.deepseek.com'}, 'appear to be reversed'),
                                ({'provider_profile': 'unknown'}, '--setup')):
            with self.subTest(change=change):
                self.store.path.write_text(json.dumps(api_config().model_dump() | change), encoding='utf-8')
                before = self.store.path.read_bytes()
                with self.assertRaisesRegex(UserConfigError, message):
                    self.store.load()
                console = self.console(['3'])
                with self.assertRaises(SetupCancelled):
                    resolve_startup(parse_args([]), store=self.store, backend=self.backend, console=console, environ={})
                self.assertEqual(self.store.path.read_bytes(), before)
                self.assertEqual(self.backend.calls, [])

    def test_invalid_saved_config_can_reenter_setup(self):
        self.store.path.write_text(json.dumps(api_config().model_dump() |
                                   {'base_url': 'deepseek-flash', 'model': 'https://api.deepseek.com'}), encoding='utf-8')
        runtime = resolve_startup(parse_args([]), store=self.store, backend=self.backend,
                                  console=self.console(['1', '6', 'y']), environ={})
        self.assertEqual(runtime.config.input_mode, 'demo')
        self.assertTrue(any('appear to be reversed' in s for s in self.output))
        self.assertEqual(self.backend.calls, [])

    def test_user_config_and_merged_overrides_use_same_rules(self):
        data = api_config().model_dump()
        for change in ({'model': 'https://example.com'},
                       {'base_url': 'model-name', 'model': 'https://example.com'}):
            with self.subTest(change=change), self.assertRaises(ValidationError):
                UserConfig.model_validate(data | change)
        normalized = UserConfig.model_validate(data | {'base_url': ' https://example.com ',
                                                       'model': ' provider/model '})
        self.assertEqual((normalized.base_url, normalized.model), ('https://example.com', 'provider/model'))
        self.store.save(api_config())
        for env in ({'LLM_MODEL': 'https://example.com'},
                    {'LLM_BASE_URL': 'model-name', 'LLM_MODEL': 'https://example.com'}):
            with self.subTest(env=env), self.assertRaises(APISettingsError):
                resolve_startup(parse_args([]), store=self.store, backend=self.backend,
                                console=self.console([]), environ=env)
            self.assertEqual(self.backend.calls, [])

    def test_cancel_and_ctrl_c_at_each_reprompt_have_no_app_or_storage_effects(self):
        for failure in ('cancel', KeyboardInterrupt(), EOFError()):
            for prefix in (['1', 'model-name'], ['1', '', 'https://example.com']):
                with self.subTest(kind=type(failure).__name__, field=len(prefix)):
                    console = self.console(prefix + [failure])
                    def resolve(args):
                        return resolve_startup(args, store=self.store, backend=self.backend, console=console, environ={})
                    with patch('autoquestion.startup.resolve_startup', side_effect=resolve), \
                         patch('autoquestion.app.main') as app, redirect_stdout(StringIO()):
                        self.assertEqual(main(['--setup']), 0)
                        app.assert_not_called()
                    self.assertFalse(self.store.path.exists())
                    self.assertEqual(self.backend.calls, [])
                    console.secret_fn.assert_not_called()

    def test_secret_like_errors_do_not_echo_into_output_or_exception(self):
        for field in ('base_url', 'model'):
            value = 'https://example.com?key=' + SECRET
            data = api_config().model_dump() | {field: value}
            self.store.path.write_text(json.dumps(data), encoding='utf-8')
            with self.assertRaises(UserConfigError) as error:
                self.store.load()
            self.assertNotIn(SECRET, str(error.exception) + repr(error.exception))
        console = self.console(['1', 'https://example.com?key=' + SECRET, 'cancel'])
        with self.assertRaises(SetupCancelled):
            run_setup(self.store, self.backend, console)
        self.assertNotIn(SECRET, str(self.output) + str(self.prompts))


if __name__ == '__main__':
    unittest.main()
