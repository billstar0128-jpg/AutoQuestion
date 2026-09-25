"""M12 tests: temp config + fake credentials only; no actual model/credential I/O."""
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import replace
from io import StringIO
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from pydantic import SecretStr, ValidationError
from autoquestion.cli import main, parse_args
from autoquestion.config import Config, ConfigError
from autoquestion.credentials import CredentialError, new_identifier
from autoquestion.doctor import user_configuration_checks
from autoquestion.provider_presets import PRESETS, ProviderPreset, build_registry
from autoquestion.setup_wizard import Console, SetupCancelled, run_setup, save_configuration, updated
from autoquestion.startup import resolve_startup, show_config, reset_config, explicit_values
from autoquestion.user_config import UserConfig, UserConfigError, UserConfigStore

SECRET = 'test-secret-value'


class FakeCredentials:
    def __init__(self):
        self.items = {}
        self.calls = []
        self.unavailable = False
        self.fail_write = False

    def __repr__(self):
        return 'FakeCredentials(redacted)'

    def list_ids(self):
        self.calls.append('list')
        if self.unavailable:
            raise CredentialError('Secure credential storage is unavailable.')
        return tuple(self.items)

    def exists(self, identifier):
        return identifier in self.list_ids()

    def get(self, identifier):
        self.calls.append('get')
        if self.unavailable:
            raise CredentialError('Secure credential storage is unavailable.')
        return self.items.get(identifier)

    def put(self, identifier, secret):
        self.calls.append('put')
        if self.unavailable or self.fail_write:
            raise CredentialError('Secure credential storage is unavailable.')
        self.items[identifier] = secret

    def delete(self, identifier):
        self.calls.append('delete')
        self.items.pop(identifier, None)


def api_config(**changes):
    return UserConfig(provider_profile='deepseek', protocol_provider='openai',
                      base_url='https://api.deepseek.com', model='test-model', supports_vision=True,
                      **changes)


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = UserConfigStore(Path(self.directory.name) / 'config.json')
        self.backend = FakeCredentials()
        self.output = []

    def console(self, answers=(), secret=SECRET):
        return Console(input_fn=Mock(side_effect=list(answers)), output=self.output.append,
                       secret_fn=Mock(return_value=SecretStr(secret)), interactive=True)

    def saved(self):
        identifier = new_identifier('deepseek')
        config = api_config(credential_mode='stored', credential_id=identifier)
        self.backend.items[identifier] = SecretStr(SECRET)
        self.store.save(config)
        return config

    def resolve(self, answers=(), args=(), env=None):
        return resolve_startup(parse_args(list(args)), store=self.store, backend=self.backend,
                               console=self.console([*answers, '']), environ={} if env is None else env)

    def assert_private(self):
        self.assertNotIn(SECRET, '\n'.join(self.output))
        if self.store.path.exists():
            self.assertNotIn(SECRET, self.store.path.read_text(encoding='utf-8'))
            self.assertNotIn('api_key', self.store.path.read_text(encoding='utf-8').lower())
        self.assertNotIn(SECRET, repr(self.backend))

    def test_registry_order_protocols_defaults_and_capability_override(self):
        self.assertEqual(tuple(PRESETS), ('deepseek', 'kimi', 'zhipu', 'openai', 'custom_openai_compatible', 'offline_demo'))
        for preset in PRESETS.values():
            with self.subTest(profile=preset.id):
                self.assertTrue(preset.display_name)
                self.assertTrue(preset.notes)
                self.assertEqual(preset.protocol_provider, 'fake' if preset.id == 'offline_demo' else 'openai')
                if preset.id not in {'offline_demo', 'custom_openai_compatible'}:
                    self.assertTrue(preset.default_base_url.startswith('https://'))
                self.assertEqual(preset.suggested_model, '')
        self.assertEqual(api_config().capabilities, {'text', 'vision'})
        self.assertEqual(updated(api_config(), supports_vision=False).capabilities, {'text'})

    def test_duplicate_and_invalid_presets_rejected(self):
        with self.assertRaises(ConfigError):
            build_registry([PRESETS['deepseek'], PRESETS['deepseek']])
        for changes in ({'id': '../bad'}, {'protocol_provider': 'anthropic'}, {'default_base_url': 'invalid'},
                        {'default_supports_vision': 'yes'}, {'display_name': ''}):
            with self.subTest(changes=changes), self.assertRaises(ConfigError):
                replace(PRESETS['deepseek'], **changes)

    def test_every_real_preset_supports_overrides_and_stores_no_secret_json(self):
        for index, preset in enumerate(tuple(PRESETS.values())[:5], 1):
            with self.subTest(profile=preset.id):
                answers = [str(index)]
                if preset.id == 'custom_openai_compatible':
                    answers.append('My gateway')
                answers += ['https://override.invalid/v1', 'my-model', 'y', '3', '1', 'y']
                result = run_setup(self.store, self.backend, self.console(answers))
                self.assertEqual(result.config.provider_profile, preset.id)
                self.assertEqual(result.config.protocol_provider, 'openai')
                self.assertEqual(result.config.base_url, 'https://override.invalid/v1')
                self.assertEqual(result.config.model, 'my-model')
                self.assertTrue(result.config.supports_vision)
                self.assertEqual(result.config.input_mode, 'dom')
                self.assertIn(result.config.credential_id, self.backend.items)
                self.assertNotIn(SECRET, repr(result))
                self.assert_private()

    def test_first_run_offline_then_second_run_skips_wizard_and_credentials(self):
        console = self.console(['6', 'y'])
        first = resolve_startup(parse_args([]), store=self.store, backend=self.backend, console=console, environ={})
        self.assertEqual((first.config.input_mode, first.config.llm_provider), ('demo', 'fake'))
        console.secret_fn.assert_not_called()
        second = self.resolve()
        self.assertEqual(second.config.input_mode, 'demo')
        self.assertEqual(self.backend.calls, [])
        self.assert_private()

    def test_stored_second_start_reads_only_selected_credential(self):
        saved = self.saved()
        result = self.resolve()
        self.assertEqual(result.config.llm_config.api_key.get_secret_value(), SECRET)
        self.assertEqual(self.backend.calls, ['get'])
        self.assertNotIn(SECRET, repr(result))
        self.assertNotIn(SECRET, repr(result.config))
        self.assertNotIn(SECRET, repr(result.config.llm_config))
        self.assertEqual(self.store.load(), saved)
        self.assert_private()

    def test_session_only_next_start_asks_key_only(self):
        self.resolve(['1', '', 'my-model', 'y', '1', '2', 'y'])
        self.assertEqual(self.store.load().credential_mode, 'session')
        console = self.console()
        result = resolve_startup(parse_args([]), store=self.store, backend=self.backend, console=console, environ={})
        console.input_fn.assert_not_called()
        console.secret_fn.assert_called_once()
        self.assertEqual(result.credential_status, 'session-only')
        self.assertNotIn('put', self.backend.calls)
        self.assert_private()

    def test_missing_credential_only_prompts_key_and_does_not_rewrite(self):
        saved = self.saved()
        self.backend.items.clear()
        result = self.resolve()
        self.assertEqual(result.credential_status, 'session-only')
        self.assertEqual(self.store.load(), saved)
        self.assert_private()

    def test_setup_keep_replace_and_switch_offline_preserve_old_credential(self):
        original = self.saved()
        console = self.console(['1', '', 'updated-model', 'y', '1', '1', 'y'])
        result = run_setup(self.store, self.backend, console, original)
        console.secret_fn.assert_not_called()
        self.assertEqual(result.config.credential_id, original.credential_id)
        replacement = run_setup(self.store, self.backend,
                                self.console(['1', '', 'new-model', 'y', '1', '2', 'y'], 'test-replacement'), result.config)
        self.assertNotEqual(replacement.config.credential_id, original.credential_id)
        self.assertEqual(self.backend.items[original.credential_id].get_secret_value(), SECRET)
        offline = run_setup(self.store, self.backend, self.console(['1', '', '', 'y', '1', '4', 'y']), replacement.config)
        self.assertEqual(offline.config.protocol_provider, 'fake')
        self.assertEqual(len(self.backend.items), 2)
        self.assert_private()

    def test_failed_replacement_leaves_old_key_and_config_intact(self):
        original = self.saved()
        before = self.store.path.read_bytes()
        self.backend.fail_write = True
        with self.assertRaises(SetupCancelled):
            run_setup(self.store, self.backend, self.console(['1', '', 'new', 'y', '1', '2', 'y', '3']), original)
        self.assertEqual(self.store.path.read_bytes(), before)
        self.assertEqual(tuple(self.backend.items), (original.credential_id,))
        self.assert_private()

    def test_backend_unavailable_session_fallback_or_retry_or_cancel(self):
        self.backend.unavailable = True
        result = self.resolve(['1', '', 'test-model', 'y', '1', '1', 'y', '1'])
        self.assertEqual(result.credential_status, 'session-only')
        self.assertEqual(self.store.load().credential_mode, 'session')
        self.assertEqual(self.backend.items, {})
        self.assert_private()

    def test_credential_retry_then_success(self):
        original_put = self.backend.put
        attempts = []
        def put(identifier, secret):
            attempts.append(1)
            if len(attempts) == 1:
                raise CredentialError('Secure credential storage is unavailable.')
            original_put(identifier, secret)
        with patch.object(self.backend, 'put', side_effect=put):
            result = self.resolve(['1', '', 'test-model', 'y', '1', '1', 'y', '2'])
        self.assertEqual(len(attempts), 2)
        self.assertEqual(result.credential_status, 'configured securely')
        self.assert_private()

    def test_recovery_of_corrupt_config_can_fallback_to_session(self):
        self.store.path.write_text('{broken')
        self.backend.unavailable = True
        result = self.resolve(['1', '1', '', 'test-model', 'y', '1', '1', 'y', '1'])
        self.assertEqual(result.credential_status, 'session-only')
        self.assertEqual(self.store.load().credential_mode, 'session')

    def test_explicit_setup_runs_again_even_with_saved_configuration(self):
        original = self.saved()
        result = self.resolve(['1', '', 'new-model', 'y', '1', '1', 'y'], args=['--setup'])
        self.assertEqual(result.config.llm_config.model, 'new-model')
        self.assertEqual(self.store.load().credential_id, original.credential_id)

    def test_process_key_overrides_stored_key_without_reading_vault(self):
        self.saved()
        with patch.object(self.backend, 'get', side_effect=AssertionError('No credential read needed')):
            result = self.resolve(env={'LLM_API_KEY': 'test-override'})
        self.assertEqual(result.config.llm_config.api_key.get_secret_value(), 'test-override')
        self.assert_private()

    def test_default_vision_unchanged_and_all_wizard_mode_choices(self):
        self.assertEqual(Config().input_mode, 'vision')
        for index, mode in enumerate(('auto', 'vision', 'dom', 'demo'), 1):
            with self.subTest(mode=mode):
                self.store.reset()
                result = self.resolve(['1', '', 'test-model', 'y', str(index), '2', 'y'])
                self.assertEqual(result.config.input_mode, mode)

    def test_setup_switches_provider_without_deleting_previous_credentials(self):
        original = self.saved()
        self.resolve(['2', '', 'kimi-model', 'y', '1', '1', 'y'], args=['--setup'])
        self.assertIn(original.credential_id, self.backend.items)
        self.assertEqual(self.store.load().provider_profile, 'kimi')
        self.assertEqual(len(self.backend.items), 2)

    def test_custom_invalid_display_name_can_be_corrected(self):
        result = self.resolve(['5', 'x'*81, 'Local gateway', 'https://example.invalid/v1',
                               'test-model', 'y', '1', '2', 'y'])
        self.assertEqual(result.display_name, 'Local gateway')
        self.assertEqual(self.store.load().display_name, 'Local gateway')
        self.assertTrue(any('最多 80' in line for line in self.output))

    def test_switch_back_with_multiple_old_keys_never_selects_arbitrary_key(self):
        original = self.saved()
        self.backend.items[new_identifier('deepseek')] = SecretStr('test-other-account')
        self.store.save(UserConfig(provider_profile='offline_demo', protocol_provider='fake',
                                   input_mode='demo', credential_mode='none'))
        result = self.resolve(['1', '', 'test-model', 'y', '1', '2', 'y'], args=['--setup'])
        self.assertEqual(result.credential_status, 'session-only')
        self.assertEqual(len(self.backend.items), 2)
        self.assertIn(original.credential_id, self.backend.items)
        self.assertNotIn('get', self.backend.calls)
        self.assertTrue(any('多个旧凭据' in line for line in self.output))
        self.assert_private()

    def test_empty_secret_reprompts_and_cancel_reset_is_noop(self):
        original = self.saved()
        console = self.console()
        console.secret_fn.side_effect = [SecretStr(''), SecretStr('   '), SecretStr(SECRET)]
        self.assertEqual(console.secret().get_secret_value(), SECRET)
        self.assertEqual(console.secret_fn.call_count, 3)
        with self.assertRaises(SetupCancelled):
            reset_config(store=self.store, backend=self.backend, console=self.console(['']))
        self.assertEqual(self.store.load(), original)
        self.assertIn(original.credential_id, self.backend.items)

    def test_vision_inconsistent_requires_explicit_continue(self):
        result = self.resolve(['1', '', 'text-model', 'n', '1', '4', '2', 'y'])
        self.assertFalse(result.config.llm_config.supports_vision)
        self.assertTrue(any('Warning:' in line for line in self.output))
        self.assertEqual(result.config.input_mode, 'auto')

    def test_cancel_and_interrupt_before_save_have_no_side_effects(self):
        for answers in (['cancel'], ['6', 'n']):
            with self.subTest(answers=answers), self.assertRaises(SetupCancelled):
                self.resolve(answers)
            self.assertFalse(self.store.path.exists())
            self.assertEqual(self.backend.items, {})
        console = self.console(['1', '', 'test-model', 'y', '1'])
        console.secret_fn.side_effect = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            run_setup(self.store, self.backend, console)
        self.assertFalse(self.store.path.exists())
        self.assertEqual(self.backend.items, {})

    def test_atomic_save_failure_rolls_back_new_credential_only(self):
        original = self.saved()
        before = self.store.path.read_bytes()
        with patch('autoquestion.user_config.os.replace', side_effect=OSError(SECRET)), self.assertRaises(UserConfigError) as error:
            save_configuration(self.store, self.backend, original, SecretStr('test-new-key'))
        self.assertNotIn(SECRET, str(error.exception))
        self.assertEqual(self.store.path.read_bytes(), before)
        self.assertEqual(tuple(self.backend.items), (original.credential_id,))
        self.assertEqual(list(self.store.path.parent.glob('.config-*.tmp')), [])

    def test_interrupt_during_save_rolls_back_staged_credential(self):
        original = self.saved()
        with patch.object(self.store, 'save', side_effect=KeyboardInterrupt()), self.assertRaises(KeyboardInterrupt):
            save_configuration(self.store, self.backend, original, SecretStr('test-new-key'))
        self.assertEqual(self.store.load(), original)
        self.assertEqual(tuple(self.backend.items), (original.credential_id,))

    def test_env_file_and_process_override_saved_without_mutating_environment(self):
        self.saved()
        fixture = self.store.path.parent / 'explicit.env'
        fixture.write_text('LLM_MODEL=file-model\nINPUT_MODE=dom\nLLM_TIMEOUT_SECONDS=15\n', encoding='utf-8')
        environment = {'INPUT_MODE': 'vision'}
        original = dict(os.environ)
        result = self.resolve(args=['--env-file', str(fixture)], env=environment)
        self.assertEqual(result.config.input_mode, 'vision')
        self.assertEqual(result.config.llm_config.model, 'file-model')
        self.assertEqual(result.config.llm_config.timeout_seconds, 15)
        self.assertEqual(os.environ, original)
        self.assertEqual(environment, {'INPUT_MODE': 'vision'})
        self.assertEqual(self.store.load().model, 'test-model')

    def test_complete_env_and_envfile_bypass_wizard_with_no_saved_config(self):
        values = api_config().to_env() | {'LLM_API_KEY': SECRET}
        result = self.resolve(env=values)
        self.assertEqual(result.config.llm_config.model, 'test-model')
        fixture = self.store.path.parent / 'explicit.env'
        fixture.write_text('\n'.join(f'{key}={value}' for key, value in values.items()), encoding='utf-8')
        self.assertEqual(self.resolve(args=['--env-file', str(fixture)]).config.input_mode, 'auto')
        self.assertFalse(self.store.path.exists())
        self.assertEqual(self.backend.calls, [])
        self.assert_private()

    def test_noninteractive_first_run_fails_without_reading_stdin(self):
        console = self.console()
        console.interactive = False
        with self.assertRaisesRegex(ConfigError, 'Windows Terminal'):
            resolve_startup(parse_args([]), store=self.store, backend=self.backend, console=console, environ={})
        console.input_fn.assert_not_called()
        console.secret_fn.assert_not_called()

    def test_invalid_json_version_profile_protocol_and_secret_field_are_safe(self):
        data = api_config().model_dump()
        for contents in ('{broken ' + SECRET, json.dumps(data | {'config_version': 99}),
                         json.dumps(data | {'provider_profile': SECRET}),
                         json.dumps(data | {'protocol_provider': 'anthropic'}),
                         json.dumps(data | {'api_key': SECRET}), json.dumps(data | {'model': ''})):
            with self.subTest(contents=contents[:12]):
                self.store.path.write_text(contents, encoding='utf-8')
                with self.assertRaises(UserConfigError) as error:
                    self.store.load()
                self.assertNotIn(SECRET, str(error.exception))

    def test_corrupt_config_ignore_cancel_or_setup_recovery(self):
        self.store.path.write_text('{broken', encoding='utf-8')
        self.assertEqual(self.resolve(['2']).config.input_mode, 'demo')
        self.assertEqual(self.store.path.read_text(), '{broken')
        with self.assertRaises(SetupCancelled):
            self.resolve(['3'])
        self.assertEqual(self.resolve(['1', '6', 'y']).config.input_mode, 'demo')
        self.assertEqual(self.store.load().provider_profile, 'offline_demo')

    def test_show_config_and_doctor_only_use_metadata_not_secret_get(self):
        self.saved()
        with patch.object(self.backend, 'get', side_effect=AssertionError('secret read forbidden')):
            show_config(parse_args(['--show-config']), store=self.store, backend=self.backend,
                        console=self.console(), environ={})
            checks, values, available = user_configuration_checks({}, store=self.store, backend=self.backend)
        self.assertTrue(available)
        self.assertIn('Credential available (metadata only)', [item.message for item in checks])
        self.assertNotIn('LLM_API_KEY', values)
        self.assert_private()

    def test_doctor_session_missing_and_corrupt_user_config(self):
        self.store.save(api_config())
        checks, _, _ = user_configuration_checks({}, store=self.store, backend=self.backend)
        self.assertIn('WARN', [item.level for item in checks])
        self.assertNotIn('FAIL', [item.level for item in checks])
        self.store.path.write_text(SECRET)
        checks, _, _ = user_configuration_checks({}, store=self.store, backend=self.backend)
        self.assertEqual(checks[0].level, 'FAIL')
        self.assertNotIn(SECRET, str(checks))

    def test_reset_defaults_keep_credentials_explicit_yes_removes_owned(self):
        original = self.saved()
        reset_config(store=self.store, backend=self.backend, console=self.console(['y', '']))
        self.assertFalse(self.store.path.exists())
        self.assertIn(original.credential_id, self.backend.items)
        reset_config(store=self.store, backend=self.backend, console=self.console(['y', 'y']))
        self.assertEqual(self.backend.items, {})

    def test_cli_commands_conflict_and_do_not_execute(self):
        for flags in (['--doctor', '--setup'], ['--show-config', '--reset-config'], ['--version', '--setup']):
            with self.subTest(flags=flags), redirect_stderr(StringIO()), self.assertRaises(SystemExit) as caught:
                parse_args(flags)
            self.assertEqual(caught.exception.code, 2)

    def test_cli_first_run_saves_then_enters_ready_without_second_launch(self):
        from autoquestion.app import Status
        from autoquestion.hotkeys import WindowsHotkeys
        console = self.console(['6', 'y'])
        def resolve(args):
            return resolve_startup(args, store=self.store, backend=self.backend, console=console, environ={})
        observed = []
        def listen(runner):
            observed.append(runner.state)
            self.assertTrue(runner.trigger())
            runner._worker.join(5)
            self.assertEqual(runner.state, Status.READY)
            runner.stop()
        with patch('autoquestion.startup.resolve_startup', side_effect=resolve), \
             patch('autoquestion.hotkeys.WindowsHotkeys') as hotkeys, \
             patch('autoquestion.browser_session.BrowserSession') as browser, self.assertLogs('autoquestion', 'INFO'):
            hotkeys.return_value.__enter__.return_value.listen.side_effect = listen
            self.assertEqual(main([]), 0)
            browser.assert_not_called()
        self.assertEqual(observed, [Status.READY])
        self.assertEqual(self.store.load().input_mode, 'demo')
        self.assert_private()

    def test_cli_sanitizes_unexpected_backend_error(self):
        output = StringIO()
        with patch('autoquestion.startup.resolve_startup', side_effect=RuntimeError(SECRET)), redirect_stderr(output):
            self.assertEqual(main(['--setup']), 1)
        self.assertNotIn(SECRET, output.getvalue())

    def test_full_doctor_with_saved_config_never_reads_secret_or_starts_setup(self):
        from autoquestion.doctor import Check, run_doctor
        from test_doctor import NoSecretRead
        self.saved()
        output = StringIO()
        with patch('autoquestion.user_config.config_path', return_value=self.store.path), \
             patch('autoquestion.credentials.WindowsCredentials', return_value=self.backend), \
             patch.object(self.backend, 'get', side_effect=AssertionError('Secret read forbidden')), \
             patch('autoquestion.doctor.dependency_check', return_value=Check('OK', 'dependencies')), \
             patch('autoquestion.doctor.chromium_check', return_value=Check('OK', 'runtime')), \
             patch('autoquestion.setup_wizard.run_setup') as wizard, redirect_stdout(output):
            self.assertEqual(run_doctor(environ=NoSecretRead({'LLM_API_KEY': object()})), 0)
            wizard.assert_not_called()
        self.assertIn('Credential available', output.getvalue())
        self.assertNotIn(SECRET, output.getvalue())

    def test_saved_runtime_reaches_existing_text_and_vision_adapters(self):
        import threading
        from autoquestion.dom import answer_dom_question
        from autoquestion.demo import make_demo_callback
        from autoquestion.vision import vision_provider
        from autoquestion.llm.fake import demo_question, FakeLLMProvider
        self.saved()
        runtime = self.resolve()
        question = demo_question()
        with patch('autoquestion.llm.openai_compatible.OpenAICompatibleProvider') as text_factory, \
             patch('autoquestion.dom.load_llm_config', side_effect=AssertionError('No env reload')), \
             patch('autoquestion.demo.load_llm_config', side_effect=AssertionError('No env reload')):
            text_factory.return_value.answer_question.return_value = FakeLLMProvider().answer_question(question)
            answer_dom_question(runtime.config, question, threading.Event(), Mock())
            make_demo_callback(runtime.config)(threading.Event())
            self.assertEqual(text_factory.call_count, 2)
            for call in text_factory.call_args_list:
                self.assertIs(call.args[0], runtime.config.llm_config)
        with patch('autoquestion.vision.OpenAICompatibleProvider') as factory, \
             patch('autoquestion.vision.load_llm_config', side_effect=AssertionError('No env reload')):
            vision_provider(runtime.config)
            factory.assert_called_once_with(runtime.config.llm_config)


if __name__ == '__main__':
    unittest.main()
