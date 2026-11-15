/** 隔离浏览器验收探针：只记录真实HTTP/WS身份并驱动公开DOM，不读取产品私有state。 */
(() => {
  const sessions = new Map(), sockets = [], sources = new Set();
  const probe = { pendingStarts: 0, codeRequestId: null, sockets, sources };
  const originalFetch = window.fetch;
  window.fetch = async (...args) => {
    const path = new URL(String(args[0] instanceof Request ? args[0].url : args[0]), location.origin).pathname;
    const starting = /\/accounts\/(?:login\/start|login-drafts\/[^/]+\/(?:resume|restart))$/.test(path);
    if (starting) probe.pendingStarts++;
    if (/\/accounts\/login\/[^/]+\/code$/.test(path) && args[1]?.body) {
      try { probe.codeRequestId = JSON.parse(args[1].body).request_id; } catch { probe.codeRequestId = null; }
    }
    try {
      const response = await originalFetch(...args);
      if (starting && response.ok) {
        const payload = await response.clone().json();
        sessions.set(payload.session_id, { environmentId: payload.environment_id });
      }
      return response;
    } finally { if (starting) probe.pendingStarts--; }
  };
  const NativeSocket = window.WebSocket;
  window.WebSocket = class extends NativeSocket {
    /** 保留真实连接，供断线及不重放验证。@param args 原构造参数。@return WebSocket。 */
    constructor(...args) { super(...args); sockets.push(this); }
  };
  const NativeSource = window.EventSource;
  window.EventSource = class extends NativeSource {
    /** 登记真实订阅。@param args 原构造参数。@return EventSource。 */
    constructor(...args) { super(...args); sources.add(this); }
    /** 释放原订阅并收口记录。@return 无。 */
    close() { super.close(); sources.delete(this); }
  };
  /** 从公开界面和真实请求恢复可观察状态。@return 当前会话观测或null。 */
  probe.readLogin = () => {
    const modal = document.querySelector('#acc-modal');
    if (!modal || modal.classList.contains('hidden')) return null;
    const terminal = !modal.querySelector('.acc-step-terminal').classList.contains('hidden');
    const sid = terminal ? modal.querySelector('#acc-login-sid').textContent : null;
    const status = modal.querySelector('#acc-code-status').textContent;
    const connection = modal.querySelector('#acc-login-connection-status').textContent;
    return {
      sid, environmentId: sessions.get(sid)?.environmentId,
      authorizationURL: terminal ? modal.querySelector('#acc-auth-url').value : null,
      connection: terminal && Boolean(connection),
      ws: [...sockets].reverse().find(socket => sid && socket.url.includes(sid)),
      starting: probe.pendingStarts > 0,
      closeRequested: modal.querySelector('#acc-modal-stage').textContent.includes('随后取消'),
      codeStatus: status.includes('已送到 CLI') ? 'delivered' : status.includes('结果未知') ? 'uncertain' : status.includes('正在发送') ? 'sending' : 'idle',
      codeSending: modal.querySelector('#acc-code-query').disabled,
      codeRequestId: probe.codeRequestId,
      term: {
        /** 通过实际终端输入节点聚焦。@return 无。 */
        focus() { modal.querySelector('.xterm-helper-textarea').focus(); },
        /** 向实际终端投递粘贴事件，业务是否接收由原连接状态决定。@param value 合成输入。@return 无。 */
        paste(value) { const data = new DataTransfer(); data.setData('text/plain', value); modal.querySelector('.xterm-helper-textarea').dispatchEvent(new ClipboardEvent('paste', { bubbles: true, clipboardData: data })); },
      },
    };
  };
  /** 使用可见分区入口刷新账号列表，保留原API及代次控制。@return 列表就绪。 */
  probe.refreshAccounts = async () => {
    const wait = async predicate => { for (let index = 0; index < 150; index++) { if (predicate()) return; await new Promise(resolve => setTimeout(resolve, 100)); } throw new Error('原生账号列表未就绪'); };
    document.querySelector('.console-sidebar a[href="/tasks"]')?.click();
    await wait(() => document.querySelector('.task-runtime [data-tab="topics"]'));
    document.querySelector('.task-runtime [data-tab="topics"]').click();
    await wait(() => document.querySelector('#topics-list'));
    document.querySelector('.task-runtime [data-tab="accounts"]').click();
    await wait(() => typeof document.querySelector('#accounts-body')?.onclick === 'function');
  };
  window.__nativeProbe = probe;
})();
