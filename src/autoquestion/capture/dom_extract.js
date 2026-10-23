// 只读取候选题组的语义标签和可见文字；不读取 HTML、输入值或浏览器存储。
(body, allQuestions = false) => {
  let incompleteText = false;
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
  const text = (element, markers = null) => {
    if (!visible(element)) return '';
    const walker = document.createTreeWalker(element, markers ? NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT : NodeFilter.SHOW_TEXT);
    const parts = [];
    let node;
    while ((node = walker.nextNode())) {
      if (node.nodeType === Node.ELEMENT_NODE) {
        if (markers?.has(node)) parts.push(`[空 ${markers.get(node)}]`);
        continue;
      }
      if (visible(node.parentElement) && !node.parentElement.closest('script, style, template, input, textarea, select, button, [contenteditable]:not([contenteditable="false"]), [role="textbox"], [role="searchbox"]')) {
        if (allQuestions && node.nodeValue.trim()) {
          const range = document.createRange();
          range.selectNodeContents(node);
          if ([...range.getClientRects()].some(r => r.top < 0 || r.left < 0 || r.bottom > innerHeight || r.right > innerWidth)) {
            incompleteText = true;
            return '';
          }
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
  const rootSelector = 'fieldset, [role="radiogroup"], [role="group"], [data-question-type], [data-question-id]';
  const fieldSelector = 'input:not([type]),input[type="text"],input[type="number"],textarea,[contenteditable]:not([contenteditable="false"]),[role="textbox"]';
  const subjectiveType = root => {
    const hint = root.getAttribute('data-question-type') || '';
    if (['fill_blank', 'short_answer'].includes(hint)) return hint;
    if (['essay', 'long_answer', '简答题', '解答题', '问答题', '简答', '解答', '问答'].includes(hint)) return 'short_answer';
    if (['填空题', '填空'].includes(hint)) return 'fill_blank';
    if (hint) return '';
    const heading = root.querySelector(':scope > legend,:scope > h1,:scope > h2,:scope > h3,:scope > h4,:scope > p,:scope > [role="heading"],:scope > [data-question-stem]');
    const match = text(heading).match(/^(?:[（(]?[\d一二三四五六七八九十]+[.)、．）]?\s*)?(填空题?|简答题?|解答题?|问答题?)(?:[：:\s（(]|$)/);
    return match ? (match[1].startsWith('填空') ? 'fill_blank' : 'short_answer') : '';
  };
  const controls = Array.from(document.querySelectorAll(selector)).filter(element =>
    visible(element) && !(element.tagName !== 'INPUT' && element.querySelector('input[type="radio"], input[type="checkbox"]'))
  );
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
  for (const root of document.querySelectorAll(rootSelector)) {
    if (!visible(root) || (allQuestions && !inViewport(root))) continue;
    const hasChoice = [...root.querySelectorAll(selector)].some(visible);
    const kind = subjectiveType(root);
    if (hasChoice) {
      if (kind) return {error: 'ambiguous_question'};
      if ([...root.querySelectorAll(fieldSelector)].some(field => visible(field) && !field.closest('label'))) {
        return {error: 'incomplete_question'};
      }
      continue;
    }
    // A wrapper around independently marked question groups is not another question.
    if ([...root.querySelectorAll(rootSelector)].some(visible)) continue;
    const fields = [...root.querySelectorAll(fieldSelector)].filter(field => visible(field) &&
      !field.parentElement.closest(fieldSelector));
    const unrelated = root.matches('[role="search"]') || root.closest('[role="search"]') ||
      (!kind && root.querySelector('input[type="password"],input[type="search"]'));
    if (unrelated) continue;
    if (!kind) {
      if (fields.length || root.hasAttribute('data-question-type') || root.hasAttribute('data-question-id')) return {error: 'incomplete_question'};
      continue;
    }
    if (root.matches('body,html,main') || !root.hasAttribute('data-question-type') &&
        !root.querySelector('legend,h1,h2,h3,h4,h5,h6,p,[data-question-stem]') &&
        !root.hasAttribute('aria-label') && !root.hasAttribute('aria-labelledby')) return {error: 'incomplete_question'};
    let blankCount = null, marked = [];
    if (kind === 'fill_blank') {
      const declared = root.getAttribute('data-blank-count');
      marked = [...root.querySelectorAll('[data-blank]')].filter(visible);
      const count = fields.length || marked.length;
      if (declared !== null && !/^(?:[1-9]|1\d|20)$/.test(declared)) return {error: 'incomplete_question'};
      blankCount = declared === null ? count : Number(declared);
      if (blankCount < 1 || blankCount > 20 || count && count !== blankCount) return {error: 'incomplete_question'};
    }
    groups.push({root, kind, controls: fields, boundaryControls: [...new Set([...fields, ...marked])], subjective: true, blankCount});
  }
  let candidates = allQuestions ? groups.filter(group => group.subjective ? inViewport(group.root) : group.controls.some(inViewport)) : groups;
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
  if (allQuestions && (group.boundaryControls || group.controls).some(control => !fullyVisible(control))) return {error: 'incomplete_question'};
  const root = group.root;
  if (group.subjective) {
    const visuals = 'canvas,img,svg,video,object,embed,iframe,input[type="image"],[role="img"]';
    if (root.matches(visuals) || [...root.querySelectorAll(visuals)].some(visible)) return {error: 'incomplete_question'};
    if (allQuestions && [...root.querySelectorAll('legend,h1,h2,h3,h4,h5,h6,[data-question-stem]')].some(
      element => visible(element) && !fullyVisible(element))) return {error: 'incomplete_question'};
    const markers = group.kind === 'fill_blank' ? new Map(group.controls.map((field, index) => [field, index + 1])) : null;
    // A group name such as “Question 4” must not replace visible conditions and
    // sub-questions. Read the whole bounded root, still excluding filled fields.
    incompleteText = false;
    const body = text(root);
    if (incompleteText) return {error: 'incomplete_question'};
    const question = body ? text(root, markers) : accessibleName(root);
    if (!question || question.length > 8000) return {error: 'incomplete_question'};
    const data = {question_text: question, kind: group.kind, options: []};
    if (group.kind === 'fill_blank') data.blank_count = group.blankCount;
    questions.push(data);
    continue;
  }
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
    if (control.labels && control.labels.length) return Array.from(control.labels).map(label => text(label)).filter(Boolean).join(' ');
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
