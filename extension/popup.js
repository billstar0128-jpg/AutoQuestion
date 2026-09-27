/* No storage, network requests, page content or secret logging in the popup. */
const status = document.getElementById('status');
async function refresh() {
  try {
    const value = await chrome.runtime.sendMessage({type: 'status'});
    status.textContent = value.connected ? 'Browser DOM Bridge: connected' : '未连接；检查 AutoQuestion 和本次配对码。';
  } catch { status.textContent = '扩展未就绪，请重新加载扩展。'; }
}
document.getElementById('pair').addEventListener('click', async () => {
  const input = document.getElementById('token');
  const token = input.value.trim();
  input.value = '';
  if (!/^[A-Za-z0-9_-]{32}$/.test(token)) {
    status.textContent = '请输入本次运行窗口中完整的 32 位配对码。'; return;
  }
  await chrome.runtime.sendMessage({type: 'pair', token});
  status.textContent = '正在连接…';
});
let site;
chrome.tabs.query({active: true, currentWindow: true}).then(tabs => {
  try {
    const url = new URL(tabs[0].url);
    if (['http:', 'https:'].includes(url.protocol)) site = `${url.protocol}//${url.hostname}/*`;
  } catch { /* Restricted pages cannot be granted. */ }
  document.getElementById('grant').disabled = !site;
});
document.getElementById('grant').addEventListener('click', () => {
  if (!site) return;
  chrome.permissions.request({origins: [site]}).then(granted => {
    status.textContent = granted ? '已允许当前站点。关掉弹窗后按 F8。' : '未授权；可使用 Vision。';
  });
});
document.getElementById('disconnect').addEventListener('click', async () => {
  await chrome.runtime.sendMessage({type: 'disconnect'}); await refresh();
});
chrome.runtime.onMessage.addListener(message => { if (message.type === 'connection') refresh(); });
refresh();
