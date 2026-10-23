/* Executed once in an isolated world on an authenticated F8 request. No mutations. */
(() => {
  'use strict';
  if (document.visibilityState !== 'visible' || !document.hasFocus()) return {status: 'changed'};
  let budget = 5000, uncertain = false;
  const candidates = [], controlSelector = 'input[type="radio"],input[type="checkbox"],[role="radio"],[role="checkbox"]';
  const rootSelector = 'fieldset,[role="radiogroup"],[role="group"],[data-question-type],[data-question-id]';
  const fieldSelector = 'input:not([type]),input[type="text"],input[type="number"],textarea,[contenteditable]:not([contenteditable="false"]),[role="textbox"]';
  const blocked = 'script,style,noscript,template,input,textarea,select,button,[contenteditable]:not([contenteditable="false"]),[role="textbox"],[role="searchbox"],[hidden],[aria-hidden="true"]';
  const normalize = value => value.replace(/\s+/g, ' ').trim();
  function spend() { if (--budget < 0) throw new Error('budget'); }
  function visible(element, clip) {
    spend();
    if (!(element instanceof element.ownerDocument.defaultView.Element)) return false;
    const view = element.ownerDocument.defaultView;
    for (let node = element; node; node = node.parentElement || node.getRootNode()?.host) {
      spend();
      const style = view.getComputedStyle(node);
      if (node.hidden || node.inert || node.getAttribute('aria-hidden') === 'true' ||
          style.display === 'none' || style.visibility !== 'visible' || Number(style.opacity) === 0) return false;
    }
    const r = element.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && r.bottom > clip.top && r.top < clip.bottom &&
      r.right > clip.left && r.left < clip.right;
  }
  function text(element, clip, markers = null) {
    if (!element || !visible(element, clip) || element.matches(blocked)) return '';
    const walker = element.ownerDocument.createTreeWalker(element, markers ? NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT : NodeFilter.SHOW_TEXT);
    const parts = [];
    while (walker.nextNode()) {
      spend();
      const node = walker.currentNode, parent = node.parentElement;
      if (node.nodeType === Node.ELEMENT_NODE) {
        if (markers?.has(node)) parts.push(`[空 ${markers.get(node)}]`);
        continue;
      }
      if (!parent || parent.closest(blocked) || !visible(parent, clip)) continue;
      // Text fragments outside the viewport are excluded even when their container is large.
      const range = element.ownerDocument.createRange(); range.selectNodeContents(node);
      const rects = [...range.getClientRects()];
      if (!rects.some(r => r.bottom > clip.top && r.top < clip.bottom &&
          r.right > clip.left && r.left < clip.right)) continue;
      if (node.textContent.trim() && rects.some(r => r.top < clip.top || r.left < clip.left ||
          r.bottom > clip.bottom || r.right > clip.right)) { uncertain = true; return ''; }
      parts.push(node.textContent);
      if (parts.join('').length > 8000) throw new Error('text budget');
    }
    return normalize(parts.join(' '));
  }
  function aria(element, clip) {
    const ids = (element.getAttribute('aria-labelledby') || '').split(/\s+/).filter(Boolean);
    if (ids.length) return normalize(ids.map(id => text(element.getRootNode().getElementById(id), clip)).join(' '));
    return normalize(element.getAttribute('aria-label') || '');
  }
  function label(control, clip) {
    const labels = [...(control.labels || [])].map(el => text(el, clip)).filter(Boolean);
    return normalize(labels.join(' ')) || aria(control, clip) ||
      (control.matches('[role]') ? text(control, clip) : '');
  }
  function group(control, clip) {
    const semantic = control.closest(rootSelector);
    if (semantic) return semantic;
    // A bounded local ancestor with a heading and at least two controls; never body/main dump.
    for (let parent = control.parentElement, depth = 0; parent && depth < 4; parent = parent.parentElement, ++depth) {
      if (parent.matches('body,html,main')) break;
      if (parent.querySelector('h1,h2,h3,h4,h5,h6') &&
          [...parent.querySelectorAll(controlSelector)].filter(el => visible(el, clip)).length >= 2) return parent;
    }
    return null;
  }
  function subjectiveType(container, clip) {
    const hint = container.getAttribute('data-question-type') || '';
    if (['fill_blank', 'short_answer'].includes(hint)) return hint;
    if (['essay', 'long_answer', '简答题', '解答题', '问答题', '简答', '解答', '问答'].includes(hint)) return 'short_answer';
    if (['填空题', '填空'].includes(hint)) return 'fill_blank';
    if (hint) return '';
    const heading = container.querySelector(':scope > legend,:scope > h1,:scope > h2,:scope > h3,:scope > h4,:scope > p,:scope > [role="heading"],:scope > [data-question-stem]');
    const match = text(heading, clip).match(/^(?:[（(]?[\d一二三四五六七八九十]+[.)、．）]?\s*)?(填空题?|简答题?|解答题?|问答题?)(?:[：:\s（(]|$)/);
    return match ? (match[1].startsWith('填空') ? 'fill_blank' : 'short_answer') : '';
  }
  function complete(element, clip) {
    const rect = element.getBoundingClientRect();
    return rect.top >= clip.top && rect.left >= clip.left && rect.bottom <= clip.bottom && rect.right <= clip.right;
  }
  function inspect(root, clip, depth = 0, offset = {left: 0, top: 0}) {
    if (depth > 3) { uncertain = true; return; }
    const elements = root.querySelectorAll('*');
    if (elements.length > 3000) throw new Error('node budget');
    const groups = new Map();
    for (const element of elements) {
      spend();
      if (!visible(element, clip)) continue;
      if (element.shadowRoot) inspect(element.shadowRoot, clip, depth + 1, offset);
      if (element.tagName === 'IFRAME') {
        try {
          const doc = element.contentDocument, rect = element.getBoundingClientRect();
          if (!doc?.body) { uncertain = true; continue; }
          // Scale/rotation cannot be mapped reliably by this bounded extractor.
          if (Math.abs(rect.width - element.offsetWidth) > 2 || Math.abs(rect.height - element.offsetHeight) > 2) {
            uncertain = true; continue;
          }
          inspect(doc, {left: Math.max(0, clip.left - rect.left), top: Math.max(0, clip.top - rect.top),
            right: Math.min(element.clientWidth, clip.right - rect.left),
            bottom: Math.min(element.clientHeight, clip.bottom - rect.top)}, depth + 1,
            {left: offset.left + rect.left, top: offset.top + rect.top});
        } catch { uncertain = true; }
      }
      if (!element.matches(controlSelector)) continue;
      const container = group(element, clip);
      if (!container) { uncertain = true; continue; }
      if (!groups.has(container)) groups.set(container, []);
      groups.get(container).push(element);
    }
    for (const [container, controls] of groups) {
      if (subjectiveType(container, clip)) { uncertain = true; continue; }
      if ([...container.querySelectorAll(fieldSelector)].some(field => visible(field, clip) && !field.closest('label'))) {
        uncertain = true; continue;
      }
      const declaredType = container.getAttribute('data-question-type');
      if (declaredType && !['single_choice', 'multiple_choice', 'true_false'].includes(declaredType)) { uncertain = true; continue; }
      // A partly off-screen question must not silently lose options.
      const rendered = [...container.querySelectorAll(controlSelector)].filter(el =>
        visible(el, {left: -Infinity, top: -Infinity, right: Infinity, bottom: Infinity}));
      if (rendered.length !== controls.length) { uncertain = true; continue; }
      if (controls.length < 2 || controls.length > 50) { uncertain = true; continue; }
      const kinds = new Set(controls.map(el => el.getAttribute('role') || el.type));
      const names = new Set(controls.filter(el => el.type === 'radio').map(el => el.name));
      if (kinds.size !== 1 || names.size > 1) { uncertain = true; continue; }
      const headings = [...container.querySelectorAll('legend,h1,h2,h3,h4,h5,h6')]
        .filter(el => visible(el, clip) && !el.closest('label'));
      const stem = aria(container, clip) || (headings.length === 1 ? text(headings[0], clip) : '');
      const options = controls.map(el => label(el, clip));
      if (!stem || stem.length > 8000 || options.some(o => !o || o.length > 2000) || new Set(options).size !== options.length) {
        uncertain = true; continue;
      }
      const rect = container.getBoundingClientRect();
      candidates.push({kind: [...kinds][0], stem, options,
        top: offset.top + rect.top, left: offset.left + rect.left});
    }
    for (const container of elements) {
      if (!container.matches(rootSelector) || !visible(container, clip)) continue;
      if ([...container.querySelectorAll(controlSelector)].some(element => visible(element, clip))) continue;
      if ([...container.querySelectorAll(rootSelector)].some(element => visible(element, clip))) continue;
      const kind = subjectiveType(container, clip);
      const fields = [...container.querySelectorAll(fieldSelector)].filter(element =>
        visible(element, {left: -Infinity, top: -Infinity, right: Infinity, bottom: Infinity}) &&
        !element.parentElement.closest(fieldSelector));
      if (container.closest('[role="search"]') || !kind && container.querySelector('input[type="password"],input[type="search"]')) continue;
      if (!kind) {
        if (fields.length || container.hasAttribute('data-question-type') || container.hasAttribute('data-question-id')) uncertain = true;
        continue;
      }
      if (container.matches('body,html,main') || !container.hasAttribute('data-question-type') &&
          !container.querySelector('legend,h1,h2,h3,h4,h5,h6,p,[data-question-stem]') &&
          !container.hasAttribute('aria-label') && !container.hasAttribute('aria-labelledby') ||
          fields.some(field => !complete(field, clip))) { uncertain = true; continue; }
      const visuals = 'canvas,img,svg,video,object,embed,iframe,input[type="image"],[role="img"]';
      if (container.matches(visuals) || [...container.querySelectorAll(visuals)].some(element => visible(element,
          {left: -Infinity, top: -Infinity, right: Infinity, bottom: Infinity}))) { uncertain = true; continue; }
      let blankCount = null;
      if (kind === 'fill_blank') {
        const declared = container.getAttribute('data-blank-count');
        const marked = [...container.querySelectorAll('[data-blank]')].filter(element => visible(element,
          {left: -Infinity, top: -Infinity, right: Infinity, bottom: Infinity}));
        if (marked.some(element => !complete(element, clip))) { uncertain = true; continue; }
        const count = fields.length || marked.length;
        if (declared !== null && !/^(?:[1-9]|1\d|20)$/.test(declared)) { uncertain = true; continue; }
        blankCount = declared === null ? count : Number(declared);
        if (blankCount < 1 || blankCount > 20 || count && count !== blankCount) { uncertain = true; continue; }
      }
      const markers = kind === 'fill_blank' ? new Map(fields.map((field, index) => [field, index + 1])) : null;
      const body = text(container, clip);
      const stem = body ? text(container, clip, markers) : aria(container, clip);
      if (!stem || stem.length > 8000) { uncertain = true; continue; }
      const rect = container.getBoundingClientRect();
      const candidate = {kind, stem, options: [], top: offset.top + rect.top, left: offset.left + rect.left};
      if (kind === 'fill_blank') candidate.blank_count = blankCount;
      candidates.push(candidate);
    }
  }
  try {
    inspect(document, {left: 0, top: 0, right: innerWidth, bottom: innerHeight});
    if (uncertain || candidates.length < 1 || candidates.length > 10) return {status: 'unavailable'};
    candidates.sort((a, b) => a.top - b.top || a.left - b.left);
    const questions = candidates.map(({top, left, ...question}) => question);
    if (new TextEncoder().encode(JSON.stringify(questions)).length > 48000) return {status: 'unavailable'};
    return questions.length === 1 ? {status: 'ok', question: questions[0]} : {status: 'ok', questions};
  } catch { return {status: 'unavailable'}; }
})()
