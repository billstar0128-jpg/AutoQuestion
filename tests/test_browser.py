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

    def test_batch_reads_single_and_multiple_separately_even_when_one_has_focus(self):
        self.page.set_content('''<fieldset><legend>题一</legend><label><input type="radio" name="one">A. 甲</label><label><input type="radio" name="one">B. 乙</label></fieldset>
        <fieldset><legend>题二</legend><label><input type="checkbox" name="two">丙</label><label><input type="checkbox" name="two">丁</label></fieldset>''')
        self.page.locator('input[name=two]').first.focus()
        questions = self.adapter.extract_questions()
        self.assertEqual([q.question_text for q in questions], ['题一', '题二'])
        self.assertEqual([q.question_type.value for q in questions], ['single_choice', 'multiple_choice'])
        self.assertEqual([[o.text for o in q.options] for q in questions], [['甲', '乙'], ['丙', '丁']])
        self.assertEqual(self.page.locator('input:checked').count(), 0)

    def test_six_visible_mixed_questions_preserve_each_type_stem_and_options(self):
        fixture = Path(__file__).resolve().parents[1] / 'examples/browser_dom/mixed_questions.html'
        self.page.set_viewport_size({'width': 1200, 'height': 900})
        self.page.set_content(fixture.read_text(encoding='utf-8'))
        self.page.locator('input[name=boiling]').first.focus()
        questions = self.adapter.extract_questions()
        self.assertEqual(len(questions), 6)
        self.assertEqual([q.question_type.value for q in questions],
                         ['single_choice', 'multiple_choice', 'true_false'] * 2)
        self.assertEqual([q.question_text.split('.')[0] for q in questions], ['1', '2', '3', '4', '5', '6'])
        self.assertEqual([[o.text for o in q.options] for q in questions],
                         [['巴黎', '伦敦', '柏林'], ['Python', 'Java', 'HTML'], ['正确', '错误'],
                          ['木星', '地球', '火星'], ['2', '3', '4'], ['正确', '错误']])
        self.assertEqual(self.page.locator('input:checked').count(), 0)

    def test_mixed_subjective_questions_do_not_read_filled_input_values(self):
        fixture = Path(__file__).resolve().parents[1] / 'examples/browser_dom/mixed_subjective.html'
        self.page.set_viewport_size({'width': 1200, 'height': 900})
        self.page.set_content(fixture.read_text(encoding='utf-8'))
        self.page.evaluate("""() => {
          document.querySelector('input[type=text]').value = 'synthetic-private-input';
          document.querySelector('textarea').value = 'synthetic-private-textarea';
          document.querySelector('[contenteditable]').textContent = 'synthetic-private-edit';
          for (const field of document.querySelectorAll('input[type=text],textarea,[contenteditable]')) {
            for (const name of ['value','textContent','innerText']) Object.defineProperty(field, name,
              {get() { throw new Error('must not read user answer'); }});
          }
        }""")
        questions = self.adapter.extract_questions()
        self.assertEqual([q.question_type.value for q in questions],
                         ['single_choice', 'multiple_choice', 'true_false', 'fill_blank', 'short_answer', 'short_answer'])
        self.assertEqual(questions[3].blank_count, 2)
        self.assertIn('[空 1]', questions[3].question_text)
        self.assertIn('[空 2]', questions[3].question_text)
        self.assertTrue(all(not q.options for q in questions[3:]))
        self.assertNotIn('synthetic-private', '\n'.join(q.model_dump_json() for q in questions))
        self.assertEqual(self.page.locator(':checked').count(), 0)

    def test_subjective_without_input_controls_and_explicit_caption(self):
        self.page.set_content('''<fieldset data-question-type="fill_blank" data-blank-count="2"><legend>两数分别为___、___。</legend></fieldset>
        <fieldset><legend>简答题：解释蒸发。</legend></fieldset>
        <fieldset data-question-type="short_answer"><legend>解答题：计算 1 + 1。</legend></fieldset>''')
        questions = self.adapter.extract_questions()
        self.assertEqual([q.question_type.value for q in questions], ['fill_blank', 'short_answer', 'short_answer'])
        self.assertEqual(questions[0].blank_count, 2)
        self.page.set_content('''<section data-question-type="short_answer" data-question-stem>解释光合作用。</section>
        <fieldset data-question-type="fill_blank"><legend>写出两种颜色：</legend><span data-blank>___</span>、<span data-blank>___</span></fieldset>''')
        questions = self.adapter.extract_questions()
        self.assertEqual([q.question_type.value for q in questions], ['short_answer', 'fill_blank'])
        self.assertEqual(questions[1].blank_count, 2)

    def test_unknown_or_incomplete_subjective_never_silently_drops_from_batch(self):
        choice = '<fieldset><legend>Single?</legend><label><input type=radio name=q>A</label><label><input type=radio name=q>B</label></fieldset>'
        for subjective in (
            '<fieldset data-question-type="fill_blank"><legend>填空题：两个数字___、___。</legend></fieldset>',
            '<fieldset data-question-type="fill_blank" data-blank-count="2"><legend>填空题：一个空。</legend><input type=text></fieldset>',
            '<fieldset data-question-id="essay"><legend>请说明原因。</legend><textarea>synthetic-private</textarea></fieldset>',
            '<fieldset data-question-type="unsupported"><legend>未知题型。</legend></fieldset>',
            '<fieldset data-question-type="fill_blank"><legend>填空题：___、___。</legend><span data-blank>___</span>'
            '<span data-blank style="position:absolute;top:2000px">___</span></fieldset>',
        ):
            with self.subTest(subjective=subjective[:70]):
                self.page.set_content(choice + subjective)
                with self.assertRaises(BrowserExtractionError):
                    self.adapter.extract_questions()

    def test_login_and_search_fields_are_not_subjective_questions(self):
        self.page.set_content('''<fieldset><legend>Single?</legend><label><input type=radio name=q>A</label><label><input type=radio name=q>B</label></fieldset>
        <fieldset><legend>Login</legend><input type=text><input type=password></fieldset>
        <fieldset role=search><legend>Search</legend><input type=search></fieldset>''')
        self.assertEqual(len(self.adapter.extract_questions()), 1)

    def test_subjective_aria_group_name_does_not_drop_conditions_or_subquestions(self):
        self.page.set_content('''<fieldset data-question-type="short_answer" aria-label="第4题">
        <legend>解答题：某车以恒定速度行驶。</legend><p data-question-stem>已知 2 小时行驶 100 千米。</p>
        <p>求平均速度，并说明计算过程。</p><textarea>synthetic-private-answer</textarea></fieldset>''')
        question = self.adapter.extract_questions()[0]
        self.assertIn('2 小时行驶 100 千米', question.question_text)
        self.assertIn('求平均速度', question.question_text)
        self.assertIn('某车以恒定速度', question.question_text)
        self.assertNotIn('synthetic-private', question.question_text)
        self.page.set_content('<fieldset data-question-type="short_answer" aria-label="第4题"><legend>解答题：计算车速。</legend>'
                              '<p style="position:absolute;top:2000px">关键条件：2小时行驶100千米。</p></fieldset>')
        with self.assertRaises(BrowserExtractionError):
            self.adapter.extract_questions()

    def test_subjective_visual_conditions_force_whole_batch_acquisition_failure(self):
        choice = '<fieldset><legend>Single?</legend><label><input type=radio name=q>A</label><label><input type=radio name=q>B</label></fieldset>'
        for visual in ('<canvas width=200 height=80></canvas>', '<img width=200 height=80 alt="必要题图">',
                       '<svg width=200 height=80><circle cx=30 cy=30 r=20></circle></svg>',
                       '<video width=200 height=80></video>', '<object width=200 height=80></object>',
                       '<iframe width=200 height=80 srcdoc="<p>Necessary material</p>"></iframe>',
                       '<embed src="data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22200%22 height=%2280%22%3E%3C/svg%3E" type="image/svg+xml" width=200 height=80>'):
            with self.subTest(visual=visual):
                self.page.set_content(choice + '<fieldset data-question-type="short_answer"><legend>解答题：根据图示计算。</legend>' + visual + '</fieldset>')
                with self.assertRaises(BrowserExtractionError):
                    self.adapter.extract_questions()
        self.page.set_content('<fieldset data-question-type="short_answer"><legend>简答题：解释蒸发。</legend>'
                              '<svg aria-hidden=true width=20 height=20></svg></fieldset>')
        self.assertEqual(len(self.adapter.extract_questions()), 1)

    def test_batch_rejects_incomplete_mixed_container_and_more_than_ten(self):
        bodies = [
            '<fieldset><legend>Mixed?</legend><label><input type=radio name=x>A</label><label><input type=radio name=x>B</label>'
            '<label><input type=checkbox>C</label><label><input type=checkbox>D</label></fieldset>',
            '<fieldset><legend>Partly visible?</legend><label><input type=radio name=x>A</label>'
            '<label style="display:block;margin-top:2000px"><input type=radio name=x>B</label></fieldset>',
            '<fieldset aria-label="Clipped stem?"><legend style="position:absolute;top:-200px">Clipped stem?</legend>'
            '<label><input type=radio name=x>A</label><label><input type=radio name=x>B</label></fieldset>',
            '<fieldset><legend>Clipped option?</legend><label style="position:relative"><input type=radio name=x>'
            '<span style="position:absolute;top:2000px">A</span></label><label><input type=radio name=x>B</label></fieldset>',
            '<style>fieldset{height:22px;padding:0;border:0} legend{float:left} label{font-size:10px}</style>' +
            ''.join(f'<fieldset><legend>Q{i}?</legend><label><input type=radio name=q{i}>A</label><label><input type=radio name=q{i}>B</label></fieldset>' for i in range(11)),
        ]
        for body in bodies:
            with self.subTest(body=body[:40]):
                self.page.set_content(body)
                with self.assertRaises(BrowserExtractionError):
                    self.adapter.extract_questions()

    def test_offscreen_questions_not_read_and_reordered_screen_order(self):
        self.page.set_content('''<fieldset><legend>Visible?</legend><label><input type=radio name=q>A</label><label><input type=radio name=q>B</label></fieldset>
        <fieldset style="margin-top:2000px"><legend>Outside viewport</legend><label><input type=radio name=x>C</label><label><input type=radio name=x>D</label></fieldset>''')
        self.assertEqual([q.question_text for q in self.adapter.extract_questions()], ['Visible?'])

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
