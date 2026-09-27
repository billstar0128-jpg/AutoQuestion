/* MV3 service worker. Events update IDs only; no page text is read until extract. */
let socket = null, token = '', connected = false, epoch = 0, windowId = -1, tabId = -1;
let heartbeat = null, retry = null, busy = false;
const VERSION = 1;
function send(message) {
  if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({v: VERSION, ...message}));
}
function notify() { chrome.runtime.sendMessage({type: 'connection'}).catch(() => {}); }
async function current() {
  const window = await chrome.windows.getLastFocused();
  if (!window.focused || window.type !== 'normal') return {window: -1, tab: -1};
  const tabs = await chrome.tabs.query({active: true, windowId: window.id});
  return tabs.length === 1 ? {window: window.id, tab: tabs[0].id} : {window: -1, tab: -1};
}
async function refresh() {
  const revision = ++epoch;
  windowId = tabId = -1;
  if (connected) send({type: 'state', epoch, window: -1, tab: -1});
  try {
    const value = await current();
    if (revision !== epoch) return;
    windowId = value.window; tabId = value.tab;
    // A distinct revision prevents replacing a previously published state in place.
    ++epoch;
    if (connected) send({type: 'state', epoch, window: windowId, tab: tabId});
  } catch { /* Metadata unavailable: stay unbound. */ }
}
chrome.windows.onFocusChanged.addListener(refresh);
chrome.tabs.onActivated.addListener(refresh);
chrome.tabs.onRemoved.addListener(id => { if (id === tabId) refresh(); });
chrome.tabs.onUpdated.addListener((id, change) => {
  if (id === tabId && (change.status || change.url)) refresh();
});
async function extract(message) {
  if (busy) return;
  busy = true;
  const link = socket;
  let result = {type: 'result', request: message.request, status: 'unavailable'};
  const same = async () => {
    const now = await current();
    return connected && link === socket && epoch === message.epoch &&
      now.window === message.window && now.tab === message.tab;
  };
  try {
    if (!await same()) result.status = 'changed';
    else if (message.type === 'check') result.status = 'unchanged';
    else {
      const results = await chrome.scripting.executeScript({
        target: {tabId: message.tab, frameIds: [0]}, files: ['extractor.js'], world: 'ISOLATED'
      });
      if (!await same()) result.status = 'changed';
      else if (results.length === 1 && results[0].result?.status === 'ok') {
        result.status = 'ok'; result.question = results[0].result.question;
      } else if (results[0]?.result?.status === 'changed') result.status = 'changed';
    }
  } catch {
    try { if (!await same()) result.status = 'changed'; } catch { result.status = 'changed'; }
  } finally {
    busy = false;
    if (link === socket && connected) send(result);
  }
}
function disconnect(forget = true) {
  if (forget) token = '';
  clearInterval(heartbeat); clearTimeout(retry);
  const previous = socket;
  socket = null; connected = false;
  previous?.close(); notify();
}
function connect() {
  disconnect(false);
  if (!token) return;
  const link = new WebSocket('ws://127.0.0.1:37841/bridge');
  socket = link;
  link.onopen = () => { if (socket === link) send({type: 'hello', token}); };
  link.onmessage = event => {
    if (socket !== link || typeof event.data !== 'string' || event.data.length > 65536) return;
    let message;
    try { message = JSON.parse(event.data); } catch { link.close(); return; }
    if (message.v !== VERSION) { link.close(); return; }
    if (message.type === 'ready' && !connected) {
      connected = true; refresh(); notify();
      heartbeat = setInterval(() => send({type: 'pong'}), 20000);
    } else if (connected && ['extract', 'check'].includes(message.type) &&
               /^[a-f0-9]{32}$/.test(message.request) &&
               ['epoch', 'window', 'tab'].every(key => Number.isSafeInteger(message[key]) && message[key] >= 0)) {
      extract(message);
    } else { link.close(); }
  };
  link.onclose = event => {
    if (socket !== link) return;
    connected = false; socket = null; clearInterval(heartbeat); notify();
    // Authentication/protocol rejection requires explicit pairing; no retry/log flood.
    if (event.code === 1008) token = '';
    else if (token) retry = setTimeout(connect, 3000);
  };
  link.onerror = () => {}; // Never log secret-bearing frames or page data.
}
chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (sender.id !== chrome.runtime.id || sender.url !== chrome.runtime.getURL('popup.html')) return;
  if (message.type === 'pair' && typeof message.token === 'string' && /^[A-Za-z0-9_-]{32}$/.test(message.token)) {
    token = message.token; connect();
  } else if (message.type === 'disconnect') disconnect();
  respond({connected});
});
