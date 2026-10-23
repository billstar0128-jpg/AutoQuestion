"""Real headless browser: local UI setup/result flow and public preview boundary."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from functools import partial
import json
import logging
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'tools'))
from playwright.sync_api import sync_playwright
from autoquestion.user_config import UserConfigStore
from autoquestion.web_ui import UIController, UIServer
from build_web_preview import build
from test_setup import FakeCredentials, SECRET
from test_web_ui import simulated_app


class SilentFiles(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class WebFrontendTests(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', '0')
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.controller = UIController(store=UserConfigStore(Path(self.directory.name) / 'config.json'),
                                       backend=FakeCredentials(), run_app=simulated_app)
        self.addCleanup(self.controller.close)
        logger = logging.getLogger('autoquestion')
        old = logger.level
        logger.setLevel(logging.INFO)
        self.addCleanup(logger.setLevel, old)
        self.server = UIServer(self.controller)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.playwright = sync_playwright().start()
        self.addCleanup(self.playwright.stop)
        self.browser = self.playwright.chromium.launch(headless=True)
        self.addCleanup(self.browser.close)
        self.page = self.browser.new_page(viewport={'width': 1440, 'height': 1000})
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(3)

    def open_local(self):
        self.page.goto(self.server.origin + '/#session=' + self.server.token)
        self.page.wait_for_function("() => document.querySelector('#provider').options.length === 6")

    def test_local_first_run_examples_safe_save_demo_and_stop(self):
        self.open_local()
        self.assertTrue(self.page.locator('#view-settings').is_visible())
        self.assertEqual(self.page.locator('#base-url').input_value(), 'https://api.deepseek.com')
        self.page.get_by_role('button', name='deepseek-flash', exact=True).click()
        self.assertEqual(self.page.locator('#model').input_value(), 'deepseek-flash')
        self.assertFalse(self.page.locator('#vision').is_checked())
        self.page.locator('#api-key').fill(SECRET)
        self.page.locator('#storage').select_option('session')
        self.page.locator('#vision').check()
        self.page.locator('#save-button').click()
        self.page.locator('#view-workspace').wait_for(state='visible')
        self.assertEqual(self.page.locator('#api-key').input_value(), '')
        self.assertNotIn(SECRET, self.controller.store.path.read_text())
        self.page.locator('#demo-button').click()
        self.page.locator('#answer-result').wait_for(state='visible')
        self.assertIn('巴黎', self.page.locator('#answer-text').inner_text())
        self.assertIn('预置', self.page.locator('#answer-reason').inner_text())
        self.assertEqual(self.page.locator('#key-status').inner_text(), '无需 Key')
        self.assertEqual(self.page.locator('#vision-capability').inner_text(), '不支持图片')
        self.assertEqual(self.controller.store.load().provider_profile, 'deepseek')
        self.page.locator('.nav-link[data-view=settings]').click()
        self.assertTrue(self.page.locator('#save-button').is_disabled())
        self.page.locator('.nav-link[data-view=workspace]').click()
        self.page.locator('#start-button').click()
        self.page.wait_for_function("() => document.querySelector('#demo-button').disabled === false")
        self.page.locator('#clear-button').click()
        self.page.locator('#empty-result').wait_for(state='visible')
        self.assertEqual(self.errors, [])

    def test_refresh_retains_session_auth_and_mobile_has_no_horizontal_overflow(self):
        self.open_local()
        self.assertNotIn('session=', self.page.url)
        self.page.reload()
        self.page.wait_for_function("() => document.querySelector('#provider').options.length === 6")
        self.page.set_viewport_size({'width': 390, 'height': 844})
        for name in ('settings', 'workspace', 'guide'):
            self.page.locator(f'.nav-link[data-view={name}]').click()
            self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'))
        self.assertEqual(self.errors, [])

    def test_result_text_cannot_inject_html_or_script(self):
        self.open_local()
        question = {'question_text': '<img src=x onerror="window.injected=true">', 'source_type': 'DOM',
                    'question_type': 'single_choice', 'options': [{'index': 0, 'label': None, 'text': '<b>test</b>'}, {'index': 1, 'label': None, 'text': 'other'}]}
        answer = {'question_type': 'single_choice', 'selected_index': 0, 'selected_label': None,
                  'selected_text': '<b>test</b>', 'selected_indices': [], 'selected_labels': [], 'selected_texts': [],
                  'short_reason': '<script>window.injected=true</script>', 'confidence': 0.5}
        with self.controller.lock:
            self.controller.history = [dict(question=question, answer=answer, time='test')]
        self.page.locator('.nav-link[data-view=workspace]').click()
        self.page.locator('#answer-result').wait_for(state='visible')
        self.assertIn('<img', self.page.locator('#question-text').inner_text())
        self.assertEqual(self.page.locator('#answer-result img, #answer-result script').count(), 0)
        self.assertFalse(self.page.evaluate('Boolean(window.injected)'))
        with self.controller.lock:
            self.controller.history[0]['question']['source_type'] = 'MANUAL'
            self.controller.history[0]['offline'] = False
        self.page.wait_for_function("() => document.querySelector('#result-source').textContent === '固定文本 Demo'")

    def test_static_preview_never_requests_local_api_or_accepts_key(self):
        output = build(Path(self.directory.name) / 'preview')
        self.assertEqual({path.name for path in output.iterdir()}, {'index.html', 'download.css', 'preview', 'try-questions.html', 'try-subjective.html'})
        self.assertNotIn('id="api-key"', (output / 'index.html').read_text(encoding='utf-8'))
        requests = []
        files = ThreadingHTTPServer(('127.0.0.1', 0), partial(SilentFiles, directory=str(output)))
        thread = threading.Thread(target=files.serve_forever, daemon=True)
        thread.start()
        try:
            self.page.on('request', lambda request: requests.append(request.url))
            self.page.goto(f'http://127.0.0.1:{files.server_port}/preview/')
            self.page.wait_for_function("() => document.querySelector('#provider').options.length === 6")
            self.assertTrue(self.page.locator('#preview-banner').is_visible())
            self.page.locator('.nav-link[data-view=settings]').click()
            self.assertTrue(self.page.locator('#api-key').is_disabled())
            self.page.locator('.nav-link[data-view=workspace]').click()
            self.page.locator('#demo-button').click()
            self.page.locator('#answer-result').wait_for(state='visible')
            self.assertFalse(any('/api/' in url for url in requests))
            self.assertFalse(self.controller.store.path.exists())
            self.assertEqual(self.errors, [])
        finally:
            files.shutdown()
            files.server_close()
            thread.join(3)

    def test_same_screen_single_and_multiple_answers_visible_together_in_order(self):
        from test_vision_batch import batch_payload
        from autoquestion.schemas import VisionBatchResult
        self.open_local()
        self.page.locator('.nav-link[data-view=workspace]').click()
        results = VisionBatchResult.model_validate(batch_payload()).model_dump(mode='json')['results']
        record = logging.LogRecord('autoquestion', logging.INFO, '', 0, 'Batch ready', (), None)
        record.question_results = results
        self.controller.record(record)
        self.page.locator('#batch-results').wait_for(state='visible')
        cards = self.page.locator('.batch-result-card')
        self.assertEqual(cards.count(), 2)
        self.assertIn('1. 法国的首都', cards.nth(0).inner_text())
        self.assertIn('A · 巴黎', cards.nth(0).inner_text())
        self.assertIn('2. 以下哪些是欧洲城市', cards.nth(1).inner_text())
        self.assertIn('A · 巴黎、B · 伦敦', cards.nth(1).inner_text())
        cards.nth(1).click()
        self.assertIn('2. 以下哪些', self.page.locator('#question-text').inner_text())
        self.assertEqual(self.page.locator('.question-option.selected').count(), 2)
        self.assertEqual([item['batch_index'] for item in self.controller.state()['history']], [1, 2])
        self.page.set_viewport_size({'width': 390, 'height': 844})
        self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        self.assertEqual(self.errors, [])

    def test_six_mixed_answers_and_longer_wait_setting(self):
        from test_vision_batch import mixed_batch_payload
        from autoquestion.schemas import VisionBatchResult
        self.open_local()
        self.assertEqual(self.page.locator('#request-timeout').input_value(), '180')
        self.page.locator('#api-key').fill(SECRET)
        self.page.locator('#model').fill('test-model')
        self.page.locator('#storage').select_option('session')
        self.page.locator('#request-timeout').fill('240')
        self.page.locator('#save-button').click()
        self.page.locator('#view-workspace').wait_for(state='visible')
        self.assertEqual(self.controller.store.load().timeout_seconds, 240)
        record = logging.LogRecord('autoquestion', logging.INFO, '', 0, 'Six questions ready', (), None)
        record.question_results = VisionBatchResult.model_validate(mixed_batch_payload()).model_dump(mode='json')['results']
        self.controller.record(record)
        cards = self.page.locator('.batch-result-card')
        self.page.wait_for_function("() => document.querySelectorAll('.batch-result-card').length === 6")
        self.assertIn('错误', cards.nth(2).inner_text())
        cards.nth(5).click()
        self.assertTrue(self.page.locator('#question-text').inner_text().startswith('6.'))
        self.assertEqual(self.page.locator('#answer-text').inner_text(), '错误')
        self.assertEqual(self.errors, [])

    def test_mobile_six_question_page_fits_without_cutting_options(self):
        self.page.set_viewport_size({'width': 390, 'height': 844})
        for name in ('mixed_questions.html', 'mixed_subjective.html'):
            with self.subTest(name=name):
                self.page.goto((ROOT / 'examples/browser_dom' / name).as_uri())
                self.assertEqual(self.page.locator('fieldset').count(), 6)
                self.assertTrue(self.page.evaluate('''() => [...document.querySelectorAll('fieldset,legend,label,fieldset p,textarea,input,[contenteditable]')].every(el => {
                    const r = el.getBoundingClientRect();
                    return r.top >= 0 && r.bottom <= innerHeight && r.left >= 0 && r.right <= innerWidth;
                })'''))
                self.assertEqual(self.page.locator('input:checked').count(), 0)

    def test_subjective_mixed_results_real_copy_paste_and_selection_survives_polling(self):
        from test_subjective_answering import subjective_mixed_payload, SOLUTION
        from autoquestion.schemas import VisionBatchResult
        self.page.context.grant_permissions(['clipboard-read', 'clipboard-write'], origin=self.server.origin)
        self.open_local()
        self.page.locator('.nav-link[data-view=workspace]').click()
        payload = subjective_mixed_payload()
        long_solution = SOLUTION + '\n' + '详细步骤保留换行与数学符号 ≤ ≥。\n' * 100 + '<b>仅为文字</b>'
        payload['results'][4]['answer']['answer_text'] = long_solution
        record = logging.LogRecord('autoquestion', logging.INFO, '', 0, 'Mixed subjective results', (), None)
        record.question_results = VisionBatchResult.model_validate(payload).model_dump(mode='json')['results']
        self.controller.record(record)
        self.page.wait_for_function("() => document.querySelectorAll('.batch-result-card').length === 6")
        self.page.locator('.batch-result-card').nth(4).click()
        self.assertEqual(self.page.locator('#answer-text').inner_text(), long_solution)
        self.assertEqual(self.page.locator('#answer-result b, #answer-result img, #answer-result script').count(), 0)
        self.page.locator('#copy-answer').click()
        self.page.wait_for_function("() => document.querySelector('#toast').textContent.includes('答案已复制')")
        # Windows clipboard uses CRLF; paste targets normalize this platform newline.
        self.assertEqual(self.page.evaluate('navigator.clipboard.readText()').replace('\r\n', '\n'), long_solution)
        self.page.evaluate("() => { const el=document.createElement('textarea'); el.id='paste-target'; document.body.append(el); }")
        self.page.locator('#paste-target').focus()
        self.page.locator('#paste-target').press('Control+V')
        self.assertEqual(self.page.locator('#paste-target').input_value(), long_solution)
        self.page.evaluate('''() => {
            window.answerPolls = 0;
            const original = window.fetch;
            window.fetch = (...args) => { if (String(args[0]).includes('/api/state')) window.answerPolls++; return original(...args); };
            const range=document.createRange(); range.selectNodeContents(document.querySelector('#answer-text'));
            const selection=window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
        }''')
        self.page.wait_for_function('() => window.answerPolls >= 2')
        self.assertEqual(self.page.evaluate('window.getSelection().toString()'), long_solution)
        self.page.locator('.batch-result-card').nth(3).click()
        self.assertEqual(self.page.locator('.blank-answer-text').all_text_contents(), ['北京', '2'])
        self.page.locator('#blank-answers button').nth(1).click()
        self.page.wait_for_function("() => navigator.clipboard.readText().then(text => text === '2')")
        self.page.locator('#copy-answer').click()
        self.page.wait_for_function("() => navigator.clipboard.readText().then(text => text.replaceAll('\\r\\n', '\\n') === '第 1 空：北京\\n第 2 空：2')")
        self.assertEqual(self.errors, [])

    def test_copy_failure_keeps_answer_selectable_and_reports_failure(self):
        from test_subjective_answering import subjective_payload
        self.open_local()
        self.page.locator('.nav-link[data-view=workspace]').click()
        data = subjective_payload()
        with self.controller.lock:
            self.controller.history = [dict(question=data['question'], answer=data['answer'], time='test')]
        self.page.locator('#answer-result').wait_for(state='visible')
        self.page.evaluate('''() => {
            Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async()=>{throw new Error('denied');}}});
            document.execCommand=()=>false;
        }''')
        self.page.locator('#copy-answer').click()
        self.page.wait_for_function("() => document.querySelector('#toast').textContent.includes('复制未完成')")
        self.assertEqual(self.page.locator('#answer-text').inner_text(), data['answer']['answer_text'])
        self.assertEqual(self.page.locator('.clipboard-fallback').count(), 0)
        self.assertEqual(self.errors, [])


if __name__ == '__main__':
    unittest.main()
