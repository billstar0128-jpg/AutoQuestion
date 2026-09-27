/* Executed once in an isolated world on an authenticated F8 request. No mutations. */
(() => {
  'use strict';
  if (document.visibilityState !== 'visible' || !document.hasFocus()) return {status: 'changed'};
  let budget = 5000, uncertain = false;
  const candidates = [], controlSelector = 'input[type="radio"],input[type="checkbox"],[role="radio"],[role="checkbox"]';
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
  function text(element, clip) {
    if (!element || !visible(element, clip) || element.matches(blocked)) return '';
    const walker = element.ownerDocument.createTreeWalker(element, NodeFilter.SHOW_TEXT);
    const parts = [];
    while (walker.nextNode()) {
      spend();
      const node = walker.currentNode, parent = node.parentElement;
      if (!parent || parent.closest(blocked) || !visible(parent, clip)) continue;
      // Text fragments outside the viewport are excluded even when their container is large.
      const range = element.ownerDocument.createRange(); range.selectNodeContents(node);
      if (![...range.getClientRects()].some(r => r.bottom > clip.top && r.top < clip.bottom &&
          r.right > clip.left && r.left < clip.right)) continue;
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
    const semantic = control.closest('fieldset,[role="radiogroup"],[role="group"]');
    if (semantic) return semantic;
    // A bounded local ancestor with a heading and at least two controls; never body/main dump.
    for (let parent = control.parentElement, depth = 0; parent && depth < 4; parent = parent.parentElement, ++depth) {
      if (parent.matches('body,html,main')) break;
      if (parent.querySelector('h1,h2,h3,h4,h5,h6') &&
          [...parent.querySelectorAll(controlSelector)].filter(el => visible(el, clip)).length >= 2) return parent;
    }
    return null;
  }
  function inspect(root, clip, depth = 0) {
    if (depth > 3) { uncertain = true; return; }
    const elements = root.querySelectorAll('*');
    if (elements.length > 3000) throw new Error('node budget');
    const groups = new Map();
    for (const element of elements) {
      spend();
      if (!visible(element, clip)) continue;
      if (element.shadowRoot) inspect(element.shadowRoot, clip, depth + 1);
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
            bottom: Math.min(element.clientHeight, clip.bottom - rect.top)}, depth + 1);
        } catch { uncertain = true; }
      }
      if (!element.matches(controlSelector)) continue;
      const container = group(element, clip);
      if (!container) { uncertain = true; continue; }
      if (!groups.has(container)) groups.set(container, []);
      groups.get(container).push(element);
    }
    for (const [container, controls] of groups) {
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
      candidates.push({kind: [...kinds][0], stem, options});
    }
  }
  try {
    inspect(document, {left: 0, top: 0, right: innerWidth, bottom: innerHeight});
    if (uncertain || candidates.length !== 1) return {status: 'unavailable'};
    const question = candidates[0];
    if (JSON.stringify(question).length > 12000) return {status: 'unavailable'};
    return {status: 'ok', question};
  } catch { return {status: 'unavailable'}; }
})()
