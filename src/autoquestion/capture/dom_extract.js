// 只读取候选题组的语义标签和可见文字；不读取 HTML、输入值或浏览器存储。
(body, allQuestions = false) => {
  const visible = element => {
    if (!element || element.closest('[hidden], [aria-hidden="true"], [inert]')) return false;
    for (let node = element; node; node = node.parentElement) {
      const style = getComputedStyle(node);
      if (style.display === 'none' || style.visibility !== 'visible' || style.opacity === '0') return false;
    }
    return element.getClientRects().length > 0;
  };
  const inViewport = element => {
    const r = element.getBoundingClientRect();
    return r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth;
  };
  const fullyVisible = element => {
    const r = element.getBoundingClientRect();
    return r.top >= 0 && r.left >= 0 && r.bottom <= innerHeight && r.right <= innerWidth;
  };
  const text = element => {
    if (!visible(element)) return '';
    const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
    const parts = [];
    let node;
    while ((node = walker.nextNode())) {
      if (visible(node.parentElement) && !node.parentElement.closest('script, style, template, input, textarea, select, button, [contenteditable]:not([contenteditable="false"]), [role="textbox"], [role="searchbox"]')) {
        if (allQuestions && node.nodeValue.trim()) {
          const range = document.createRange();
          range.selectNodeContents(node);
          if ([...range.getClientRects()].some(r => r.top < 0 || r.left < 0 || r.bottom > innerHeight || r.right > innerWidth)) return '';
        }
        parts.push(node.nodeValue);
      }
    }
    return parts.join(' ').replace(/\s+/g, ' ').trim();
  };
  const accessibleName = element => {
    const ids = (element.getAttribute('aria-labelledby') || '').trim().split(/\s+/).filter(Boolean);
    if (ids.length) return ids.map(id => text(document.getElementById(id))).join(' ').trim();
    return (element.getAttribute('aria-label') || '').trim();
  };
  const selector = 'input[type="radio"], input[type="checkbox"], [role="radio"], [role="checkbox"]';
  const controls = Array.from(document.querySelectorAll(selector)).filter(element =>
    visible(element) && !(element.tagName !== 'INPUT' && element.querySelector('input[type="radio"], input[type="checkbox"]'))
  );
  if (!controls.length) return {error: 'no_question'};
  if (controls.length > 200) return {error: 'too_many_controls'};
  const groups = [];
  for (const control of controls) {
    const kind = control.tagName === 'INPUT' ? control.type : control.getAttribute('role');
    let root = control.parentElement.closest('fieldset, [role="radiogroup"], [role="group"], [data-question-type], [data-question-id]');
    const name = control.tagName === 'INPUT' && !(root && kind === 'checkbox') ? control.name : '';
    // 无语义容器时按 radio name/form 分组，再寻找公共父节点。
    if (!root && !name) root = control.parentElement;
    let group = groups.find(item => item.root === root && item.name === name && item.kind === kind && item.form === control.form);
    if (!group) {
      group = {root, name, kind, form: control.form, controls: []};
      groups.push(group);
    }
    group.controls.push(control);
  }
  for (const group of groups) {
    if (!group.root) {
      let root = group.controls[0].parentElement;
      while (root && !group.controls.every(control => root.contains(control))) root = root.parentElement;
      group.root = root;
    }
  }
  let candidates = allQuestions ? groups.filter(group => group.controls.some(inViewport)) : groups;
  if (!candidates.length) return {error: 'no_question'};
  if (!allQuestions && groups.length > 1) {
    const active = document.activeElement;
    const focused = groups.filter(group => active !== document.body && active !== document.documentElement &&
      group.root.contains(active));
    const marked = groups.filter(group => group.root.getAttribute('aria-current') === 'true' ||
      group.root.getAttribute('data-current') === 'true');
    candidates = focused.length === 1 ? focused : marked.length === 1 ? marked : groups;
  }
  if (!allQuestions && candidates.length !== 1) return {error: 'ambiguous_question'};
  if (allQuestions && (candidates.length > 10 || candidates.some((group, i) =>
    candidates.some((other, j) => i !== j && (group.root.contains(other.root) || other.root.contains(group.root)))))) {
    return {error: 'ambiguous_question'};
  }
  if (allQuestions) candidates.sort((a, b) => {
    const left = a.root.getBoundingClientRect(), right = b.root.getBoundingClientRect();
    return left.top - right.top || left.left - right.left;
  });
  const questions = [];
  for (const group of candidates) {
  if (allQuestions && group.controls.some(control => !fullyVisible(control))) return {error: 'incomplete_question'};
  const root = group.root;
  const legend = root.querySelector(':scope > legend');
  const heading = root.querySelector(':scope > h1, :scope > h2, :scope > h3, :scope > h4, :scope > [role="heading"], :scope > p');
  if (allQuestions && ([legend, heading].some(element => element && visible(element) && !fullyVisible(element)) ||
      group.controls.some(control => [...(control.labels || [])].some(label => visible(label) && !fullyVisible(label))))) {
    return {error: 'incomplete_question'};
  }
  const question = accessibleName(root) || text(legend) || text(heading);
  const options = group.controls.map(control => {
    const aria = accessibleName(control);
    if (aria) return aria;
    if (control.labels && control.labels.length) return Array.from(control.labels).map(text).filter(Boolean).join(' ');
    return control.tagName === 'INPUT' ? '' : text(control);
  });
  if (!question || options.length < 2 || options.some(option => !option)) return {error: 'incomplete_question'};
  if (question.length > 8000 || options.some(option => option.length > 2000) || options.length > 50) {
    return {error: 'too_large'};
  }
  questions.push({question_text: question, kind: group.kind, options,
          hint: root.getAttribute('data-question-type') || ''});
  }
  return allQuestions ? {questions} : questions[0];
}
