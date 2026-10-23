"""Real Chromium executes the exact shipped extractor against synthetic local content."""
import json
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from playwright.sync_api import sync_playwright
from autoquestion import __version__
from autoquestion.capture.browser import question_from_dom

ROOT = Path(__file__).resolve().parents[1]


class ExtensionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', '0')
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)
        cls.script = (ROOT / 'extension/extractor.js').read_text(encoding='utf-8')

    @classmethod
    def tearDownClass(cls):
        cls.browser.close(); cls.playwright.stop()

    def setUp(self):
        self.page = self.browser.new_page(viewport={'width': 1200, 'height': 900})
        self.addCleanup(self.page.close)

    def read(self):
        return self.page.evaluate(self.script)

    def test_manifest_permissions_and_no_background_content_scripts(self):
        manifest = json.loads((ROOT / 'extension/manifest.json').read_text())
        self.assertEqual(manifest['manifest_version'], 3)
        self.assertEqual(set(manifest['permissions']), {'activeTab', 'scripting'})
        for forbidden in ('host_permissions', 'content_scripts', 'externally_connectable', 'web_accessible_resources'):
            self.assertNotIn(forbidden, manifest)
        self.assertEqual(manifest['version'], __version__)

    def test_fixtures_and_unselected_controls(self):
        for name, kind in [('single_choice', 'single_choice'), ('multiple_choice', 'multiple_choice'),
                           ('true_false', 'true_false'), ('no_labels', 'single_choice'), ('noise_page', 'single_choice')]:
            with self.subTest(page=name):
                self.page.goto((ROOT / f'examples/browser_dom/{name}.html').as_uri())
                result = self.read()
                self.assertEqual(result['status'], 'ok')
                q = result['question']
                question = question_from_dom(dict(question_text=q['stem'], kind=q['kind'], options=q['options']))
                self.assertEqual(question.question_type.value, kind)
                self.assertEqual(self.page.locator(':checked').count(), 0)
                self.assertNotIn('synthetic-private', json.dumps(result))
                self.assertNotIn('synthetic-password', json.dumps(result))
                if name == 'no_labels':
                    self.assertTrue(all(o.label is None for o in question.options))

    def test_canvas_empty_questions_and_hidden(self):
        self.page.goto((ROOT / 'examples/browser_dom/canvas_question.html').as_uri())
        self.assertEqual(self.read()['status'], 'unavailable')
        for body in ('<h1>No question</h1>', '<fieldset hidden><legend>Hidden?</legend><label><input type=radio>A</label><label><input type=radio>B</label></fieldset>'):
            self.page.set_content(body)
            self.assertEqual(self.read()['status'], 'unavailable')

    def test_nested_labels_aria_heading_sensitive_values_and_viewport(self):
        self.page.set_content('<section><h2>Nested?</h2><label><input type=radio name=x><span>A. One</span>'
                              '<span hidden>private-hidden</span><input type=password value=private-password>'
                              '<span contenteditable>private-edited</span><span role=textbox>private-textbox</span></label>'
                              '<label><input type=radio name=x><b>B. Two</b></label></section>')
        self.assertEqual(self.read()['question']['options'], ['A. One', 'B. Two'])
        self.page.locator('input[type=radio]').first.evaluate('el => el.disabled = true')
        self.assertEqual(self.read()['question']['options'], ['A. One', 'B. Two'])
        self.page.set_content('<div role=radiogroup aria-labelledby=stem><h2 id=stem>Yes or no?</h2>'
                              '<div role=radio aria-label=Yes></div><div role=radio aria-label=No></div></div>'
                              '<style>[role=radio]{height:30px}</style>')
        self.assertEqual(self.read()['question']['options'], ['Yes', 'No'])
        self.page.locator('[role=radiogroup]').evaluate("el => el.style.marginTop='2000px'")
        self.assertEqual(self.read()['status'], 'unavailable')

    def test_spa_reads_new_dom_and_open_shadow(self):
        self.page.goto((ROOT / 'examples/browser_dom/spa_like_question.html').as_uri())
        self.assertEqual(len(self.read()['question']['options']), 4)
        self.page.click('#next')
        self.assertEqual(self.read()['question']['options'], ['正确', '错误'])
        self.page.set_content('<div id=host></div>')
        self.page.evaluate("document.querySelector('#host').attachShadow({mode:'open'}).innerHTML = '<fieldset><legend>Shadow?</legend><label><input type=radio name=x>Yes</label><label><input type=radio name=x>No</label></fieldset>'")
        self.assertEqual(self.read()['question']['stem'], 'Shadow?')

    def test_partly_offscreen_options_are_not_silently_dropped(self):
        self.page.set_content('<fieldset><legend>All options required?</legend>'
                              '<label><input type=radio name=x>A</label><label><input type=radio name=x>B</label>'
                              '<label style="display:block;margin-top:2000px"><input type=radio name=x>C</label></fieldset>')
        self.assertEqual(self.read()['status'], 'unavailable')

    def test_batch_keeps_independent_questions_and_screen_order(self):
        self.page.set_content('<fieldset><legend>Single?</legend><label><input type=radio name=q>A. One</label>'
                              '<label><input type=radio name=q>B. Two</label></fieldset>'
                              '<fieldset><legend>Multiple?</legend><label><input type=checkbox>C. Three</label>'
                              '<label><input type=checkbox>D. Four</label></fieldset>')
        self.page.locator('input[type=checkbox]').first.focus()
        result = self.read()
        self.assertEqual(result['status'], 'ok')
        self.assertNotIn('question', result)
        self.assertEqual([q['stem'] for q in result['questions']], ['Single?', 'Multiple?'])
        self.assertEqual([q['kind'] for q in result['questions']], ['radio', 'checkbox'])
        self.assertEqual([q['options'] for q in result['questions']], [['A. One', 'B. Two'], ['C. Three', 'D. Four']])
        self.assertEqual(self.page.locator(':checked').count(), 0)

    def test_six_visible_mixed_questions_keep_all_boundaries_without_selection(self):
        self.page.goto((ROOT / 'examples/browser_dom/mixed_questions.html').as_uri())
        self.page.locator('input[name=boiling]').first.focus()
        result = self.read()
        self.assertEqual(result['status'], 'ok')
        questions = [question_from_dom(dict(question_text=q['stem'], kind=q['kind'], options=q['options']))
                     for q in result['questions']]
        self.assertEqual([q.question_type.value for q in questions],
                         ['single_choice', 'multiple_choice', 'true_false'] * 2)
        self.assertEqual([q.question_text.split('.')[0] for q in questions], ['1', '2', '3', '4', '5', '6'])
        self.assertEqual([[o.text for o in q.options] for q in questions],
                         [['巴黎', '伦敦', '柏林'], ['Python', 'Java', 'HTML'], ['正确', '错误'],
                          ['木星', '地球', '火星'], ['2', '3', '4'], ['正确', '错误']])
        self.assertEqual(self.page.locator(':checked').count(), 0)

    def test_subjective_batch_blank_count_and_filled_answers_remain_private(self):
        self.page.goto((ROOT / 'examples/browser_dom/mixed_subjective.html').as_uri())
        self.page.evaluate("""() => {
          document.querySelector('input[type=text]').value = 'synthetic-private-input';
          document.querySelector('textarea').value = 'synthetic-private-textarea';
          document.querySelector('[contenteditable]').textContent = 'synthetic-private-edit';
          for (const field of document.querySelectorAll('input[type=text],textarea,[contenteditable]')) {
            for (const name of ['value','textContent','innerText']) Object.defineProperty(field, name,
              {get() { throw new Error('must not read user answer'); }});
          }
        }""")
        result = self.read()
        self.assertEqual(result['status'], 'ok')
        questions = result['questions']
        self.assertEqual([q['kind'] for q in questions], ['radio', 'checkbox', 'radio', 'fill_blank', 'short_answer', 'short_answer'])
        self.assertEqual(questions[3]['blank_count'], 2)
        self.assertIn('[空 1]', questions[3]['stem'])
        self.assertIn('[空 2]', questions[3]['stem'])
        self.assertTrue(all(not q['options'] for q in questions[3:]))
        self.assertNotIn('synthetic-private', json.dumps(result))
        self.assertEqual(self.page.locator(':checked').count(), 0)

    def test_subjective_declared_no_control_and_unmarked_or_incomplete_fails(self):
        self.page.set_content('<fieldset data-question-type="fill_blank" data-blank-count="2"><legend>填空题：___和___。</legend></fieldset>'
                              '<fieldset><legend>解答题：计算 1 + 1。</legend></fieldset>')
        self.assertEqual([q['kind'] for q in self.read()['questions']], ['fill_blank', 'short_answer'])
        self.page.set_content('<section data-question-type="short_answer" data-question-stem>解释光合作用。</section>'
                              '<fieldset data-question-type="fill_blank"><legend>写出两种颜色：</legend><span data-blank>___</span>、<span data-blank>___</span></fieldset>')
        self.assertEqual([q['kind'] for q in self.read()['questions']], ['short_answer', 'fill_blank'])
        self.assertEqual(self.read()['questions'][1]['blank_count'], 2)
        choice = '<fieldset><legend>Single?</legend><label><input type=radio name=q>A</label><label><input type=radio name=q>B</label></fieldset>'
        for subjective in (
            '<fieldset data-question-type="fill_blank"><legend>填空题：___。</legend></fieldset>',
            '<fieldset data-question-type="fill_blank" data-blank-count="2"><legend>填空题：___。</legend><input type=text></fieldset>',
            '<fieldset data-question-id="essay"><legend>请说明原因。</legend><textarea>synthetic-private</textarea></fieldset>',
            '<fieldset data-question-type="unknown"><legend>未知题型。</legend></fieldset>',
            '<fieldset data-question-type="fill_blank"><legend>填空题：___、___。</legend><span data-blank>___</span>'
            '<span data-blank style="position:absolute;top:2000px">___</span></fieldset>',
        ):
            with self.subTest(subjective=subjective[:65]):
                self.page.set_content(choice + subjective)
                self.assertEqual(self.read()['status'], 'unavailable')

    def test_login_and_search_fields_do_not_become_questions(self):
        self.page.set_content('<fieldset><legend>Single?</legend><label><input type=radio name=q>A</label><label><input type=radio name=q>B</label></fieldset>'
                              '<fieldset><legend>Login</legend><input type=text><input type=password></fieldset>'
                              '<fieldset role=search><legend>Search</legend><input type=search></fieldset>')
        self.assertEqual(self.read()['status'], 'ok')
        self.assertEqual(self.read()['question']['stem'], 'Single?')

    def test_subjective_group_aria_name_keeps_full_visible_material(self):
        self.page.set_content('<fieldset data-question-type="short_answer" aria-label="第4题">'
                              '<legend>解答题：某车以恒定速度行驶。</legend><p data-question-stem>已知 2 小时行驶 100 千米。</p>'
                              '<p>求平均速度，并说明过程。</p><textarea>synthetic-private-answer</textarea></fieldset>')
        question = self.read()['question']
        self.assertIn('2 小时行驶 100 千米', question['stem'])
        self.assertIn('求平均速度', question['stem'])
        self.assertIn('某车以恒定速度', question['stem'])
        self.assertNotIn('synthetic-private', question['stem'])

    def test_subjective_visuals_refuse_text_only_subset_but_aria_hidden_decorations_are_ignored(self):
        choice = '<fieldset><legend>Single?</legend><label><input type=radio name=q>A</label><label><input type=radio name=q>B</label></fieldset>'
        for visual in ('<canvas width=200 height=80></canvas>', '<img width=200 height=80 alt="必要题图">',
                       '<svg width=200 height=80><circle cx=30 cy=30 r=20></circle></svg>',
                       '<video width=200 height=80></video>', '<object width=200 height=80></object>',
                       '<iframe width=200 height=80 srcdoc="<p>Necessary material</p>"></iframe>',
                       '<embed src="data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22200%22 height=%2280%22%3E%3C/svg%3E" type="image/svg+xml" width=200 height=80>'):
            with self.subTest(visual=visual):
                self.page.set_content(choice + '<fieldset data-question-type="short_answer"><legend>解答题：根据图示计算。</legend>' + visual + '</fieldset>')
                self.assertEqual(self.read()['status'], 'unavailable')
        self.page.set_content('<fieldset data-question-type="short_answer"><legend>简答题：解释蒸发。</legend>'
                              '<svg aria-hidden=true width=20 height=20></svg></fieldset>')
        self.assertEqual(self.read()['status'], 'ok')

    def test_batch_limits_and_shared_mixed_container_fail_closed(self):
        self.page.set_content('<fieldset><legend>Mixed?</legend><label><input type=radio name=q>A</label>'
                              '<label><input type=radio name=q>B</label><label><input type=checkbox>C</label>'
                              '<label><input type=checkbox>D</label></fieldset>')
        self.assertEqual(self.read()['status'], 'unavailable')
        self.page.set_content('<style>fieldset{height:22px;padding:0;border:0}legend{float:left}label{font-size:10px}</style>' +
                              ''.join(f'<fieldset><legend>Q{i}?</legend><label><input type=radio name=q{i}>A</label>'
                                      f'<label><input type=radio name=q{i}>B</label></fieldset>' for i in range(11)))
        self.assertEqual(self.read()['status'], 'unavailable')

    def test_same_origin_frame_and_closed_shadow_unavailable(self):
        self.page.set_content('<iframe srcdoc="<fieldset><legend>Frame?</legend><label><input type=radio name=x>Yes</label><label><input type=radio name=x>No</label></fieldset>" width=800 height=300></iframe>')
        self.page.frame_locator('iframe').locator('legend').wait_for()
        self.assertEqual(self.read()['question']['stem'], 'Frame?')
        self.page.set_content('<iframe sandbox="allow-scripts" srcdoc="<fieldset><legend>Opaque origin?</legend><label><input type=radio>Yes</label><label><input type=radio>No</label></fieldset>" width=800 height=300></iframe>')
        self.assertEqual(self.read()['status'], 'unavailable')
        self.page.set_content('<div id=host></div>')
        self.page.evaluate("document.querySelector('#host').attachShadow({mode:'closed'}).innerHTML = '<fieldset><legend>Closed?</legend><label><input type=radio>Yes</label><label><input type=radio>No</label></fieldset>'")
        self.assertEqual(self.read()['status'], 'unavailable')
