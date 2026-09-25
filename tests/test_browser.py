"""真实 headless Chromium + 本地页面；导航模拟人工翻题，不操作答案。"""
from pathlib import Path
import os
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', '0')
from playwright.sync_api import sync_playwright
from autoquestion.browser_session import DEMO_PATH, BrowserSession
from autoquestion.capture.browser import BrowserDOMAdapter, BrowserExtractionError, parse_options
from autoquestion.schemas import SourceType, QuestionType


class OptionPrefixTests(unittest.TestCase):
    def test_explicit_prefix_forms(self):
        for texts in (['A. 巴黎', 'B.伦敦'], ['A、巴黎', 'B．伦敦'], ['A 巴黎', 'B 伦敦'],
                      ['(A) 巴黎', '(B)伦敦']):
            with self.subTest(texts=texts):
                options = parse_options(texts)
                self.assertEqual([o.label for o in options], ['A', 'B'])
                self.assertEqual([o.text for o in options], ['巴黎', '伦敦'])
                self.assertEqual([o.index for o in options], [0, 1])

    def test_ambiguous_or_absent_prefix_is_preserved(self):
        texts = ['Python', 'C', 'HTML', 'Java', 'C language', 'Aardvark']
        self.assertEqual([o.label for o in parse_options(texts)], [None] * len(texts))
        self.assertEqual([o.text for o in parse_options(texts)], texts)


class BrowserDOMTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        try:
            cls.browser = cls.playwright.chromium.launch(headless=True)
        except Exception:
            cls.playwright.stop()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.context = self.browser.new_context()
        self.addCleanup(self.context.close)
        self.context.route('**/*', lambda route: route.continue_() if route.request.url == DEMO_PATH.as_uri() else route.abort())
        self.page = self.context.new_page()
        self.adapter = BrowserDOMAdapter(self.page)

    def test_demo_four_questions_and_navigation_without_answer_actions(self):
        self.page.goto(DEMO_PATH.as_uri())
        self.assertEqual(self.page.locator('fieldset').count(), 4)
        expected = [
            ('法国的首都是哪里？', 'single_choice', ['巴黎', '伦敦', '柏林', '罗马'], ['A','B','C','D']),
            ('太阳系中最大的行星是？', 'single_choice', ['木星','地球','火星','金星'], [None]*4),
            ('以下哪些属于编程语言？', 'multiple_choice', ['Python','C','HTML','Java'], [None]*4),
            ('地球绕太阳公转。', 'true_false', ['正确','错误'], [None]*2),
        ]
        for i, (stem, kind, texts, labels) in enumerate(expected):
            with self.subTest(question=i):
                self.assertEqual(self.page.locator('fieldset:visible').count(), 1)
                question = self.adapter.extract_question()
                self.assertEqual(question.question_text, stem)
                self.assertEqual(question.question_type.value, kind)
                self.assertEqual(question.source_type, SourceType.DOM)
                self.assertEqual([o.index for o in question.options], list(range(len(texts))))
                self.assertEqual([o.text for o in question.options], texts)
                self.assertEqual([o.label for o in question.options], labels)
                self.assertEqual(self.page.locator('input:checked').count(), 0)
            if i < 3:
                self.page.get_by_role('button', name='下一题').click()  # 仅模拟用户导航。
        self.assertTrue(self.page.get_by_role('button', name='下一题').is_disabled())
        self.page.get_by_role('button', name='上一题').click()
        self.assertEqual(self.adapter.extract_question().question_type, QuestionType.MULTIPLE_CHOICE)

    def test_demo_without_demo_attributes(self):
        self.page.goto(DEMO_PATH.as_uri())
        self.page.locator('fieldset').evaluate_all("nodes => nodes.forEach(n => {n.removeAttribute('data-question-id'); n.removeAttribute('data-question-type')})")
        for kind in ('single_choice', 'single_choice', 'multiple_choice', 'true_false'):
            self.assertEqual(self.adapter.extract_question().question_type.value, kind)
            if kind != 'true_false':
                self.page.get_by_role('button', name='下一题').click()

    def test_external_labels_and_aria_labelledby(self):
        self.page.set_content('''<h2 id="stem">选择城市</h2><div role="radiogroup" aria-labelledby="stem">
        <input id="x" type="radio" name="city"><label for="x">A、巴黎</label>
        <input id="y" type="radio" name="city"><label for="y">B．伦敦</label></div>''')
        result = self.adapter.extract_question()
        self.assertEqual(result.question_text, '选择城市')
        self.assertEqual([o.text for o in result.options], ['巴黎', '伦敦'])

    def test_custom_aria_radio_group(self):
        self.page.set_content('''<div role="radiogroup" aria-label="太阳系中最大的行星是？">
        <div role="radio" aria-label="木星" tabindex="0"></div>
        <div role="radio" tabindex="0">地球</div></div>''')
        # 空 custom control 有可见尺寸，aria-label 提供语义名字。
        self.page.add_style_tag(content='[role=radio]{display:block;width:100px;height:30px}')
        result = self.adapter.extract_question()
        self.assertEqual([o.text for o in result.options], ['木星', '地球'])
        self.assertEqual([o.label for o in result.options], [None, None])

    def test_name_group_and_parent_heading_without_special_attributes(self):
        self.page.set_content('''<section><h2>选择一个</h2>
        <label><input type="radio" name="q">甲</label><label><input type="radio" name="q">乙</label></section>''')
        self.assertEqual(self.adapter.extract_question().question_text, '选择一个')

    def test_checkbox_semantic_group_with_different_names(self):
        self.page.set_content('''<fieldset><legend>选择语言</legend>
        <label><input type="checkbox" name="python">Python</label>
        <label><input type="checkbox" name="c">C</label></fieldset>''')
        self.assertEqual(self.adapter.extract_question().question_type, QuestionType.MULTIPLE_CHOICE)

    def test_hidden_content_and_input_values_excluded(self):
        self.page.set_content('''<fieldset><legend>可见题目<span hidden>PRIVATE_HIDDEN</span></legend>
        <label><input type="radio" name="q" value="PRIVATE_VALUE">甲<span aria-hidden="true">PRIVATE_LABEL</span></label>
        <label><input type="radio" name="q">乙</label><input type="password" value="PRIVATE_PASSWORD">
        <input type="hidden" value="PRIVATE_TOKEN"></fieldset>
        <fieldset hidden><legend>PRIVATE_QUESTION</legend><input type="radio" name="secret"></fieldset>''')
        result = self.adapter.extract_question()
        self.assertEqual(result.question_text, '可见题目')
        self.assertNotIn('PRIVATE', result.model_dump_json())

    def test_dynamic_rendered_dom_and_mutation_are_read(self):
        self.page.set_content('''<main id="quiz"></main><script>
        setTimeout(() => { document.getElementById('quiz').innerHTML = '<fieldset><legend>动态题干</legend><label><input type="radio" name="q">甲</label><label><input type="radio" name="q">乙</label></fieldset>'; }, 10);
        </script>''')
        self.page.locator('legend').wait_for()
        self.assertEqual(self.adapter.extract_question().question_text, '动态题干')
        self.page.locator('legend').evaluate("node => node.textContent = '更新后的题干'")
        self.assertEqual(self.adapter.extract_question().question_text, '更新后的题干')

    def test_ambiguous_groups_rejected_until_one_is_focused(self):
        self.page.set_content('''<fieldset><legend>题一</legend><label><input type="radio" name="one">甲</label><label><input type="radio" name="one">乙</label></fieldset>
        <fieldset><legend>题二</legend><label><input type="radio" name="two">丙</label><label><input type="radio" name="two">丁</label></fieldset>''')
        with self.assertRaisesRegex(BrowserExtractionError, '多个题组'):
            self.adapter.extract_question()
        self.page.locator('input[name=two]').first.focus()
        self.assertEqual(self.adapter.extract_question().question_text, '题二')
        self.assertEqual(self.page.locator('input:checked').count(), 0)

    def test_absent_incomplete_and_conflicting_questions(self):
        for html in ('<p>没有题目</p>', '<input type=password value=private-value>',
                     '<fieldset><label><input type=radio name=q>甲</label><label><input type=radio name=q>乙</label></fieldset>',
                     '<fieldset><legend>重复标签</legend><label><input type=radio name=q>A. 甲</label><label><input type=radio name=q>A. 乙</label></fieldset>',
                     '<fieldset><legend>缺标签</legend><input type=radio name=q><input type=radio name=q></fieldset>',
                     '<fieldset data-question-type="multiple_choice"><legend>冲突</legend><label><input type=radio name=q>甲</label><label><input type=radio name=q>乙</label></fieldset>'):
            with self.subTest(html=html):
                self.page.set_content(html)
                with self.assertRaises(BrowserExtractionError):
                    self.adapter.extract_question()

    def test_page_closed_is_clear_error(self):
        self.page.close()
        with self.assertRaisesRegex(BrowserExtractionError, '页面已关闭'):
            self.adapter.extract_question()

    def test_disconnected_browser_is_clear_error(self):
        other = self.playwright.chromium.launch(headless=True)
        page = other.new_page()
        adapter = BrowserDOMAdapter(page)
        other.close()
        with self.assertRaises(BrowserExtractionError):
            adapter.extract_question()


class ManagedBrowserTests(unittest.TestCase):
    def test_managed_page_runs_on_one_thread_and_closes(self):
        import threading
        session = BrowserSession(headless=True)
        self.addCleanup(session.close)
        session.start()
        self.assertEqual(session.extract_question().source_type, SourceType.DOM)
        owners = []
        def read():
            owners.append(session._call(threading.get_ident))
            return session.extract_question().question_text
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=3) as callers:
            results = [callers.submit(read) for _ in range(3)]
            for result in results:
                self.assertEqual(result.result(timeout=15), '法国的首都是哪里？')
        self.assertEqual(len(set(owners)), 1)
        session.close()
        self.assertFalse(any(t.name.startswith('autoquestion-browser') for t in threading.enumerate()))
        with self.assertRaises(BrowserExtractionError):
            session.extract_question()

    def test_managed_browser_rejects_navigation_away_from_demo(self):
        session = BrowserSession(headless=True)
        self.addCleanup(session.close)
        session.start()
        session._call(lambda: session._adapter.page.goto('about:blank'))
        with self.assertRaises(BrowserExtractionError):
            session.extract_question()


if __name__ == '__main__':
    unittest.main()
