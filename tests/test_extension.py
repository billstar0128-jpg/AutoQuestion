"""Real Chromium executes the exact shipped extractor against synthetic local content."""
import json
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from playwright.sync_api import sync_playwright
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
        self.assertEqual(manifest['version'], '0.2.0')

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

    def test_canvas_empty_multiple_questions_and_hidden(self):
        self.page.goto((ROOT / 'examples/browser_dom/canvas_question.html').as_uri())
        self.assertEqual(self.read()['status'], 'unavailable')
        for body in ('<h1>No question</h1>', '<fieldset hidden><legend>Hidden?</legend><label><input type=radio>A</label><label><input type=radio>B</label></fieldset>',
                     '<fieldset><legend>Q?</legend><label><input type=radio>A</label><label><input type=radio>B</label></fieldset>' * 2):
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

    def test_same_origin_frame_and_closed_shadow_unavailable(self):
        self.page.set_content('<iframe srcdoc="<fieldset><legend>Frame?</legend><label><input type=radio name=x>Yes</label><label><input type=radio name=x>No</label></fieldset>" width=800 height=300></iframe>')
        self.page.frame_locator('iframe').locator('legend').wait_for()
        self.assertEqual(self.read()['question']['stem'], 'Frame?')
        self.page.set_content('<iframe sandbox="allow-scripts" srcdoc="<fieldset><legend>Opaque origin?</legend><label><input type=radio>Yes</label><label><input type=radio>No</label></fieldset>" width=800 height=300></iframe>')
        self.assertEqual(self.read()['status'], 'unavailable')
        self.page.set_content('<div id=host></div>')
        self.page.evaluate("document.querySelector('#host').attachShadow({mode:'closed'}).innerHTML = '<fieldset><legend>Closed?</legend><label><input type=radio>Yes</label><label><input type=radio>No</label></fieldset>'")
        self.assertEqual(self.read()['status'], 'unavailable')
