/**
 * vibecoding-bench WebUI
 * 纯原生 JS + Hash 路由 + Fetch + SSE
 */

const API = (path, opts = {}) =>
  fetch('/api' + path, {
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
    ...opts,
  }).then(async (r) => {
    // 401:session 过期或未登录 → 全局弹登录框,中止当前调用
    if (r.status === 401 && !path.startsWith('/auth/')) {
      showAuthModal();
      throw new Error('auth required');
    }
    if (!r.ok) {
      let msg = `${r.status} ${r.statusText}`;
      try { const j = await r.json(); msg = j.detail || msg; } catch {}
      throw new Error(msg);
    }
    return r.json();
  });

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const state = {
  accounts: [],
  cc2apiAccounts: [],
  topics: [],
  tasks: [],
  batches: [],
  runs: [],
  runtimeModel: null,
  runtimeEffort: null,
  claudeCodeVersion: null,
  topicFilter: '',
  runsEventSource: null,
  runDetail: null,
};

// ===================== 路由 =====================
const ROUTES = {
  accounts: renderAccounts,
  topics: renderTopics,
  tasks: renderTasks,
  runs: renderRuns,
};

function currentTab() {
  const hash = (location.hash || '#accounts').replace(/^#/, '');
  return ROUTES[hash] ? hash : 'accounts';
}

function navigate() {
  const tab = currentTab();
  $$('.tabs a').forEach(a => a.classList.toggle('active', a.dataset.tab === tab));
  const view = $('#view');
  view.innerHTML = '';
  const tpl = $(`#tpl-${tab}`);
  if (tpl) view.appendChild(tpl.content.cloneNode(true));

  // 切换页面时关掉运行流
  if (tab !== 'runs' && state.runsEventSource) {
    state.runsEventSource.close();
    state.runsEventSource = null;
  }
  if (tab !== 'runs') endRunDetail();
  ROUTES[tab]();
}

window.addEventListener('hashchange', navigate);

// ===================== Accounts =====================
function formatDuration(sec) {
  if (typeof sec !== 'number' || Number.isNaN(sec)) return '未知';
  const abs = Math.abs(sec);
  const day = Math.floor(abs / 86400);
  const hour = Math.floor((abs % 86400) / 3600);
  const minute = Math.floor((abs % 3600) / 60);
  if (day > 0) return `${day}d ${hour}h`;
  if (hour > 0) return `${hour}h ${minute}m`;
  return `${Math.max(0, minute)}m`;
}

function renderOauthTokenStatus(a) {
  const stateClass = {
    valid: 'pill-success',
    expiring: 'pill-timeout',
    expired: 'pill-failed',
    missing: 'pill-queued',
    invalid: 'pill-failed',
  }[a.oauth_token_state] || 'pill-queued';
  const stateLabel = {
    valid: '有效',
    expiring: '将过期',
    expired: '已过期',
    missing: '未登录',
    invalid: '异常',
  }[a.oauth_token_state] || '未知';
  if (!a.oauth_expires_at_ms) {
    return `<span class="pill ${stateClass}">${stateLabel}</span><div class="muted">无过期时间</div>`;
  }
  const expiresAt = new Date(a.oauth_expires_at_ms);
  const expiresText = Number.isNaN(expiresAt.getTime()) ? '未知时间' : expiresAt.toLocaleString();
  const remain = a.oauth_expires_in_sec <= 0
    ? `超时 ${formatDuration(a.oauth_expires_in_sec)}`
    : `剩余 ${formatDuration(a.oauth_expires_in_sec)}`;
  return `
    <span class="pill ${stateClass}">${stateLabel}</span>
    <div>${escapeHTML(expiresText)}</div>
    <div class="muted">${escapeHTML(remain)}</div>
  `;
}

function formatWarmupTime(value) {
  if (typeof value !== 'number') return '-';
  const date = new Date(value * 1000);
  return Number.isNaN(date.getTime()) ? '-' : date.toLocaleString();
}

function renderWarmupStatus(account) {
  if (account.cc2api_account_id == null) {
    return '<span class="pill pill-queued">未绑定</span>';
  }
  const enabled = Number(account.warmup_enabled || 0) === 1;
  const status = String(account.warmup_last_status || (enabled ? 'scheduled' : 'off'));
  const statusClass = {
    off: 'pill-queued',
    scheduled: 'pill-success',
    preparing: 'pill-running',
    queued: 'pill-queued',
    running: 'pill-running',
    success: 'pill-success',
    failed: 'pill-failed',
    timeout: 'pill-timeout',
    stopped: 'pill-timeout',
    auth_failed: 'pill-failed',
    sync_failed: 'pill-timeout',
    paused: 'pill-failed',
  }[status] || (enabled ? 'pill-success' : 'pill-queued');
  const error = account.warmup_last_error
    ? `<div class="warmup-error" title="${escapeHTML(account.warmup_last_error)}">${escapeHTML(account.warmup_last_error)}</div>`
    : '';
  return `
    <div><code>cc#${escapeHTML(account.cc2api_account_id)}</code> <span class="pill ${statusClass}">${escapeHTML(status)}</span></div>
    <div>${escapeHTML(account.warmup_interval_min_hours || 3)}-${escapeHTML(account.warmup_interval_max_hours || 5)}h</div>
    <div class="muted">next ${escapeHTML(formatWarmupTime(account.warmup_next_run_at))}</div>
    ${error}
  `;
}

async function renderAccounts() {
  try {
    state.accounts = await API('/accounts');
  } catch (e) { return alert('加载账号失败: ' + e.message); }

  const body = $('#accounts-body');
  body.innerHTML = state.accounts.map(a => `
    <tr>
      <td>${a.id}</td>
      <td><strong>${escapeHTML(a.name)}</strong></td>
      <td><code>${escapeHTML(a.profile_path)}</code></td>
      <td>${renderProxyEndpoint(a)}</td>
      <td>${renderAccountTimezone(a)}</td>
      <td>${renderOauthTokenStatus(a)}</td>
      <td class="warmup-status">${renderWarmupStatus(a)}</td>
      <td>${a.enabled ? '✓' : '✗'}</td>
      <td><div class="op-actions account-actions">
        <button class="btn btn-sm" data-quota="${a.id}">额度</button>
        <button class="btn btn-sm" data-cc2-sync="${a.id}">同步</button>
        <button class="btn btn-sm" data-warmup-config="${a.id}">养号</button>
        ${a.cc2api_account_id != null && Number(a.warmup_enabled || 0) === 1 ? `<button class="btn btn-sm btn-primary" data-warmup-now="${a.id}">立即运行</button>` : ''}
        ${a.cc2api_account_id != null && Number(a.warmup_enabled || 0) !== 1 ? `<button class="btn btn-sm" data-warmup-resume="${a.id}">恢复</button>` : ''}
        ${a.cc2api_account_id == null ? `<button class="btn btn-sm" data-relogin="${a.id}">重授权</button>` : ''}
        ${a.cc2api_account_id != null ? `<button class="btn btn-sm btn-danger" data-cc2-unbind="${a.id}">解绑</button>` : ''}
        <button class="btn btn-sm btn-danger" data-del="${a.id}">删除</button>
      </div></td>
    </tr>
  `).join('') || '<tr><td colspan="9" class="muted empty-cell">暂无账号</td></tr>';

  body.onclick = async (e) => {
    const id = e.target.dataset.del;
    const quotaId = e.target.dataset.quota;
    const reloginId = e.target.dataset.relogin;
    const syncId = e.target.dataset.cc2Sync;
    const warmupConfigId = e.target.dataset.warmupConfig;
    const warmupNowId = e.target.dataset.warmupNow;
    const warmupResumeId = e.target.dataset.warmupResume;
    const unbindId = e.target.dataset.cc2Unbind;
    if (quotaId) {
      e.target.disabled = true;
      try {
        const quota = await API(`/accounts/${quotaId}/quota`, { method: 'POST' });
        openQuotaDetail(quotaId, quota);
      } catch (err) {
        alert('查询额度失败: ' + err.message);
      } finally {
        e.target.disabled = false;
      }
      return;
    }
    if (reloginId) {
      const account = state.accounts.find(a => String(a.id) === String(reloginId));
      if (account) openAccLoginModal(account);
      return;
    }
    if (syncId) {
      e.target.disabled = true;
      try {
        const result = await API(`/accounts/${syncId}/cc2api/sync`, { method: 'POST' });
        alert(result.created ? '已创建 cc2api 账号并完成绑定' : '已关联现有 cc2api 账号并同步凭据');
        await renderAccounts();
      } catch (err) {
        alert('同步 cc2api 失败: ' + err.message);
      } finally {
        e.target.disabled = false;
      }
      return;
    }
    if (warmupConfigId) {
      const account = state.accounts.find(a => String(a.id) === String(warmupConfigId));
      if (account) await openWarmupModal(account);
      return;
    }
    if (warmupNowId) {
      e.target.disabled = true;
      try {
        const result = await API(`/accounts/${warmupNowId}/warmup/run`, { method: 'POST' });
        if (!result.started) {
          alert(result.warmup_last_error || `未启动：${result.warmup_last_status || '账号当前不可认领'}`);
        }
        await renderAccounts();
      } catch (err) {
        alert('立即运行失败: ' + err.message);
      } finally {
        e.target.disabled = false;
      }
      return;
    }
    if (warmupResumeId) {
      e.target.disabled = true;
      try {
        await API(`/accounts/${warmupResumeId}/warmup/resume`, { method: 'POST' });
        await renderAccounts();
      } catch (err) {
        alert('恢复养号失败: ' + err.message);
      } finally {
        e.target.disabled = false;
      }
      return;
    }
    if (unbindId && confirm(`解绑账号 #${unbindId} 的 cc2api 账号并停止未来养号?`)) {
      e.target.disabled = true;
      try {
        await API(`/accounts/${unbindId}/cc2api-binding`, { method: 'DELETE' });
        await renderAccounts();
      } catch (err) {
        alert('解绑失败: ' + err.message);
      } finally {
        e.target.disabled = false;
      }
      return;
    }
    if (id && confirm(`删除账号 #${id}?`)) {
      await API(`/accounts/${id}`, { method: 'DELETE' });
      await renderAccounts();
    }
  };

  $('#add-account').onclick = () => openAccLoginModal();
  $('#acc-form').onsubmit = (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const body = {};
    for (const [k, v] of fd) {
      if (!v) continue;
      if (k.endsWith('_port')) body[k] = Number(v);
      else if (k === 'force_reauth') body[k] = v === 'true';
      else body[k] = v;
    }
    startAccLogin(body);
  };
  // Proxy URL 粘贴解析:输入即触发,实时回填下面 5 个字段
  const urlInput = $('#acc-proxy-url');
  if (urlInput) {
    urlInput.addEventListener('input', () => applyProxyUrl(urlInput.value));
  }
  $('#acc-login-cancel').onclick = () => endAccLogin({ alsoCloseModal: true });
  $('#acc-login-commit').onclick = () => commitAccLogin();
  $('#acc-modal-close').onclick = () => endAccLogin({ alsoCloseModal: true });
  $('#warmup-form').onsubmit = saveWarmupConfig;
}

async function openWarmupModal(account) {
  try {
    state.cc2apiAccounts = await API('/cc2api/accounts');
  } catch (e) {
    return alert('加载 cc2api 账号失败: ' + e.message);
  }
  const form = $('#warmup-form');
  form.account_id.value = account.id;
  form.interval_min_hours.value = account.warmup_interval_min_hours || 3;
  form.interval_max_hours.value = account.warmup_interval_max_hours || 5;
  form.enabled.checked = Number(account.warmup_enabled || 0) === 1;
  const options = state.cc2apiAccounts.map(item => `
    <option value="${escapeHTML(item.id)}">#${escapeHTML(item.id)} ${escapeHTML(item.name || 'oauth')} · ${escapeHTML(item.email_masked || '-')}</option>
  `).join('');
  form.cc2api_account_id.innerHTML = options || (
    account.cc2api_account_id != null
      ? `<option value="${escapeHTML(account.cc2api_account_id)}">#${escapeHTML(account.cc2api_account_id)} 当前绑定</option>`
      : '<option value="">暂无可用账号</option>'
  );
  if (account.cc2api_account_id != null) {
    const exists = state.cc2apiAccounts.some(item => String(item.id) === String(account.cc2api_account_id));
    if (!exists) {
      form.cc2api_account_id.insertAdjacentHTML(
        'afterbegin',
        `<option value="${escapeHTML(account.cc2api_account_id)}">#${escapeHTML(account.cc2api_account_id)} 当前绑定</option>`,
      );
    }
    form.cc2api_account_id.value = String(account.cc2api_account_id);
  }
  $('#warmup-modal-title').textContent = `#${account.id} ${account.name}`;
  openModal('#warmup-modal');
}

async function saveWarmupConfig(e) {
  e.preventDefault();
  const form = e.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  const accountId = Number(form.account_id.value);
  const payload = {
    cc2api_account_id: Number(form.cc2api_account_id.value),
    enabled: form.enabled.checked,
    interval_min_hours: Number(form.interval_min_hours.value),
    interval_max_hours: Number(form.interval_max_hours.value),
  };
  button.disabled = true;
  try {
    await API(`/accounts/${accountId}/warmup`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    });
    closeModal('#warmup-modal');
    await renderAccounts();
  } catch (err) {
    alert('保存养号配置失败: ' + err.message);
  } finally {
    button.disabled = false;
  }
}

function renderProxyEndpoint(account) {
  if (!account.upstream_socks5_host) {
    return '<span class="muted">未配置</span>';
  }
  const scheme = account.upstream_proxy_scheme || 'socks5';
  const port = account.upstream_socks5_port ? `:${escapeHTML(account.upstream_socks5_port)}` : '';
  return `<code>${escapeHTML(scheme)}://${escapeHTML(account.upstream_socks5_host)}${port}</code>`;
}

function renderAccountTimezone(account) {
  const timezone = account.effective_timezone || account.timezone || '-';
  const mode = account.timezone_mode === 'manual' ? 'manual' : 'auto';
  return `
    <code>${escapeHTML(timezone)}</code>
    <div class="muted">${escapeHTML(mode)}</div>
  `;
}

function openQuotaDetail(accountId, quota) {
  endRunDetail();
  const row = state.accounts.find(a => String(a.id) === String(accountId));
  const formatResetAt = (value) => {
    if (!value) return '-';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return new Intl.DateTimeFormat('zh-CN', {
      timeZone: 'Asia/Shanghai',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    }).format(date).replace(/\//g, '-');
  };
  const fmt = (v) => {
    if (!v) return '<span class="muted">暂无数据 / 需一次 API 响应后可用</span>';
    const used = v.used_percentage ?? v.utilization ?? '-';
    return `
      <div>used: <strong>${escapeHTML(used)}%</strong></div>
      <div>reset: <code>${escapeHTML(formatResetAt(v.resets_at))}</code> <span class="muted">UTC+8</span></div>
    `;
  };
  $('#modal-content').innerHTML = `
    <h3>Quota <code>${escapeHTML(row?.name || `acc#${accountId}`)}</code></h3>
    ${quota.ok ? '' : `<div class="detail-section"><pre>${escapeHTML(quota.message || 'usage API 未返回额度窗口')}</pre></div>`}
    <div class="stats-grid">
      <div class="stat-box"><div class="stat-label">5h</div><div class="stat-value-sm">${fmt(quota.five_hour)}</div></div>
      <div class="stat-box"><div class="stat-label">7d</div><div class="stat-value-sm">${fmt(quota.seven_day)}</div></div>
      <div class="stat-box"><div class="stat-label">7d sonnet</div><div class="stat-value-sm">${fmt(quota.seven_day_sonnet)}</div></div>
      <div class="stat-box"><div class="stat-label">7d fable</div><div class="stat-value-sm">${fmt(quota.seven_day_fable)}</div></div>
    </div>
  `;
  openModal('#modal');
}

/**
 * 解析 http / socks5 / socks5h URL,成功则回填 acc-form 的 5 个字段。
 * 支持格式:
 *   http://user:pass@host:port
 *   socks5://user:pass@host:port
 *   socks5h://user:pass@host:port
 *   http://host:port              (无凭据)
 *   socks5://user:pass@host       (省略端口 → 1080)
 * 失败静默不动 — 让用户手填或继续粘贴。
 */
function parseProxyUrl(s) {
  if (!s) return null;
  let url;
  try {
    url = new URL(String(s).trim());
  } catch (_e) {
    return null;
  }
  const scheme = url.protocol.replace(':', '').toLowerCase();
  if (!['http', 'socks5', 'socks5h'].includes(scheme)) return null;
  if (!url.hostname) return null;
  if (!['', '/'].includes(url.pathname) || url.search || url.hash) return null;
  const port = url.port ? Number(url.port) : (scheme === 'http' ? 8080 : 1080);
  if (!Number.isInteger(port) || port < 1 || port > 65535) return null;
  return {
    scheme,
    user: decodeUrlPart(url.username),
    pass: decodeUrlPart(url.password),
    host: url.hostname,
    port,
  };
}

function decodeUrlPart(value) {
  try {
    return decodeURIComponent(value || '');
  } catch (_e) {
    return value || '';
  }
}

function applyProxyUrl(raw) {
  const parsed = parseProxyUrl(raw);
  if (!parsed) return false;
  const form = $('#acc-form');
  if (!form) return false;
  form.elements['upstream_proxy_scheme'].value = parsed.scheme;
  form.elements['upstream_socks5_host'].value = parsed.host;
  form.elements['upstream_socks5_port'].value = String(parsed.port);
  form.elements['upstream_socks5_user'].value = parsed.user;
  form.elements['upstream_socks5_pass'].value = parsed.pass;
  return true;
}

// ============== OAuth 登录两步流（acc-modal） ==============
// 流程：
//   step 1: 用户填 name + proxy → POST /api/accounts/login/start → 拿 session_id
//   step 2: 打开 WS PTY → 用户在 xterm 里走 claude auth login → 点 commit
//   commit: POST /api/accounts/login/{sid}/commit → 校验 → 写库 → 关容器
// 取消任意一步都 DELETE /api/accounts/login/{sid} 清场。
function openAccLoginModal(account = null) {
  // 重置到 step 1
  const form = $('#acc-form');
  showAccStep('config');
  form.reset();
  state.accLogin = account ? { mode: 'relogin', accountId: account.id } : { mode: 'new' };
  form.elements.upstream_proxy_scheme.value = account?.upstream_proxy_scheme || 'socks5';
  form.elements.timezone.value = account?.timezone || '';
  if (account) {
    form.elements.name.value = account.name || '';
    form.elements.upstream_socks5_host.value = account.upstream_socks5_host || '';
    form.elements.upstream_socks5_port.value = account.upstream_socks5_port || '';
    form.elements.upstream_socks5_user.value = account.upstream_socks5_user || '';
    form.elements.upstream_socks5_pass.value = account.upstream_socks5_pass || '';
  }
  form.elements.name.readOnly = Boolean(account);
  $('#acc-force-reauth').value = account ? 'true' : 'false';
  $('.modal-titlebar-name', $('#acc-modal')).firstChild.textContent = account ? 'acc / relogin ' : 'acc / new ';
  $('#acc-modal-stage').textContent = 'step 1 · configure';
  openModal('#acc-modal');
}

function showAccStep(which) {
  // which = 'config' | 'terminal'
  $('.acc-step-config').classList.toggle('hidden', which !== 'config');
  $('.acc-step-terminal').classList.toggle('hidden', which !== 'terminal');
}

async function startAccLogin(body) {
  const loginState = state.accLogin || {};
  state.accLogin = loginState;
  let resp;
  try {
    resp = await API('/accounts/login/start', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  } catch (e) {
    return alert('启动登录会话失败: ' + e.message);
  }
  // 保存 proxy/name 给 commit 用
  state.accLogin.body = body;
  state.accLogin.mode = loginState.mode || 'new';
  state.accLogin.accountId = loginState.accountId || null;
  state.accLogin.sid = resp.session_id;
  state.accLogin.name = resp.name;

  $('#acc-login-sid').textContent = resp.session_id;
  $('#acc-login-sidecar').textContent = resp.has_sidecar ? 'yes' : 'no (direct)';
  $('#acc-login-name').textContent = resp.name;
  $('#acc-modal-stage').textContent = 'step 2 · terminal';

  showAccStep('terminal');
  await attachAccLoginTerminal(resp.ws_path);
}

async function attachAccLoginTerminal(wsPath) {
  const termState = await attachTerminal('#acc-login-xterm', wsPath);

  state.accLogin.term = termState.term;
  state.accLogin.fit = termState.fit;
  state.accLogin.ws = termState.ws;

  // 粘贴本地回显:claude TUI 的 "Paste code here >" 默认不回显粘贴内容,
  // 用户看不到自己粘了啥。在 xterm 内部 textarea 上挂 paste 监听,把文本以
  // 暗色写到屏幕(本地回显);onData 仍把数据照常透传给后端 PTY,服务端不变。
  const host = $('#acc-login-xterm');
  const ta = host.querySelector('textarea.xterm-helper-textarea');
  if (ta) {
    ta.addEventListener('paste', (e) => {
      const text = (e.clipboardData || window.clipboardData)?.getData('text') || '';
      if (text) {
        // \x1b[2m = dim, \x1b[0m = reset; 粘贴文本可能含换行,统一成 CRLF
        termState.term.write(`\x1b[2m${text.replace(/\r?\n/g, '\r\n')}\x1b[0m`);
      }
    });
  }

  state.accLogin.onResize = termState.onResize;
}

async function attachTerminal(hostSelector, wsPath) {
  if (typeof Terminal === 'undefined') {
    await new Promise(r => {
      const t = setInterval(() => {
        if (typeof Terminal !== 'undefined' && typeof FitAddon !== 'undefined') {
          clearInterval(t); r();
        }
      }, 50);
    });
  }

  const host = $(hostSelector);
  host.innerHTML = '';

  const term = new Terminal({
    fontFamily: '"JetBrains Mono", ui-monospace, Menlo, monospace',
    fontSize: 13,
    cursorBlink: true,
    convertEol: true,
    theme: {
      background: '#0a0b09',
      foreground: '#e8e1cf',
      cursor: '#ffb649',
      black: '#0a0b09', red: '#ff6b58', green: '#7cd97c', yellow: '#ffc164',
      blue: '#5fa8d7', magenta: '#d77cd7', cyan: '#5fd7d7', white: '#e8e1cf',
    },
  });
  const fit = new FitAddon.FitAddon();
  term.loadAddon(fit);
  term.open(host);
  fit.fit();

  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const ws = new WebSocket(`${proto}//${location.host}${wsPath}`);
  ws.binaryType = 'arraybuffer';

  ws.onopen = () => {
    ws.send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }));
    term.focus();
  };
  ws.onmessage = (e) => {
    if (e.data instanceof ArrayBuffer) {
      term.write(new Uint8Array(e.data));
    } else if (typeof e.data === 'string') {
      try {
        const msg = JSON.parse(e.data);
        if (msg.type === 'error') term.write(`\r\n\x1b[31m[orchestrator] ${msg.msg}\x1b[0m\r\n`);
      } catch { term.write(e.data); }
    }
  };
  ws.onclose = () => {
    term.write('\r\n\x1b[90m[ws closed]\x1b[0m\r\n');
  };
  ws.onerror = () => {
    term.write(`\r\n\x1b[31m[ws error]\x1b[0m\r\n`);
  };
  term.onData((data) => {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'input', data }));
    }
  });

  const onResize = () => {
    try { fit.fit(); } catch {}
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }));
    }
  };
  window.addEventListener('resize', onResize);
  return { term, fit, ws, onResize };
}

async function commitAccLogin() {
  const al = state.accLogin;
  if (!al || !al.sid) return;
  const btn = $('#acc-login-commit');
  btn.disabled = true;
  try {
    const r = await API(`/accounts/login/${al.sid}/commit`, {
      method: 'POST',
      body: JSON.stringify(al.body || { name: al.name }),
    });
    const action = al.mode === 'relogin' ? 'reauthorized' : 'saved';
    if (al.term) al.term.write(`\r\n\x1b[32m[ok] account ${action} (#${r.id}) · auth=${r.auth_method}\x1b[0m\r\n`);
    // commit 成功后服务端已清容器；前端关 WS + 弹窗 + 刷列表
    endAccLogin({ alsoCloseModal: true, skipServerCancel: true });
    renderAccounts();
  } catch (e) {
    btn.disabled = false;
    alert('提交失败: ' + e.message + '\n\n如果还没登录成功，请先在终端完成 OAuth。');
  }
}

function endAccLogin({ alsoCloseModal = false, skipServerCancel = false } = {}) {
  const al = state.accLogin || {};
  // 1. 关闭 WS
  if (al.ws && al.ws.readyState <= 1) {
    try { al.ws.close(); } catch {}
  }
  // 2. 释放 xterm
  if (al.term) { try { al.term.dispose(); } catch {} }
  if (al.onResize) window.removeEventListener('resize', al.onResize);
  // 3. 通知后端清容器（commit 路径已清，不重复）
  if (al.sid && !skipServerCancel) {
    API(`/accounts/login/${al.sid}`, { method: 'DELETE' }).catch(() => {});
  }
  state.accLogin = null;
  if (alsoCloseModal) closeModal('#acc-modal');
  // 重置 step
  showAccStep('config');
  $('#acc-modal-stage').textContent = 'step 1 · configure';
  $('#acc-login-commit').disabled = false;
}

// ===================== Topics =====================
async function renderTopics() {
  if (state.topics.length === 0) {
    try { state.topics = await API('/topics'); }
    catch (e) { return alert('加载题库失败: ' + e.message); }
  }

  $('#topics-count').textContent = `(${state.topics.length})`;
  const list = $('#topics-list');
  const filter = state.topicFilter.toLowerCase();

  list.innerHTML = state.topics
    .filter(t => !filter ||
      t.title.toLowerCase().includes(filter) ||
      t.category.toLowerCase().includes(filter) ||
      String(t.no).includes(filter))
    .map(t => `
      <div class="topic-card" data-id="${t.id}">
        <div class="topic-no">#${t.no}</div>
        <div class="topic-title">${escapeHTML(t.title)}</div>
        <div class="topic-desc">${escapeHTML(t.description)}</div>
        <div class="topic-cat">${escapeHTML(t.category)}</div>
      </div>
    `).join('') || '<div class="muted empty-panel">暂无 topic</div>';

  list.onclick = (e) => {
    const card = e.target.closest('.topic-card');
    if (!card) return;
    openTopicModal(Number(card.dataset.id));
  };

  $('#topic-filter').oninput = (e) => {
    state.topicFilter = e.target.value;
    renderTopics();
  };
  $('#topic-filter').value = state.topicFilter;
  $('#add-topic').onclick = () => openTopicModal(null);
}

function openTopicModal(topicId) {
  const topic = topicId ? state.topics.find(t => t.id === topicId) : null;
  const form = $('#topic-form');
  form.reset();
  form.topic_id.value = topic ? topic.id : '';
  form.no.value = topic ? topic.no : nextTopicNo();
  form.title.value = topic ? topic.title : '';
  form.description.value = topic ? topic.description : '';
  form.category.value = topic ? topic.category : '';
  $('#topic-modal-title').textContent = topic ? `#${topic.no}` : 'new';
  $('#topic-delete').classList.toggle('hidden', !topic);
  openModal('#topic-modal');

  form.onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    const body = {
      no: Number(fd.get('no')),
      title: fd.get('title'),
      description: fd.get('description') || '',
      category: fd.get('category') || '',
      enabled: true,
    };
    try {
      if (topic) {
        await API(`/topics/${topic.id}`, { method: 'PUT', body: JSON.stringify(body) });
      } else {
        await API('/topics', { method: 'POST', body: JSON.stringify(body) });
      }
      closeModal('#topic-modal');
      state.topics = [];
      await renderTopics();
    } catch (err) {
      alert('保存题目失败: ' + err.message);
    }
  };

  $('#topic-delete').onclick = async () => {
    if (!topic || !confirm(`删除 topic #${topic.no}?`)) return;
    try {
      await API(`/topics/${topic.id}`, { method: 'DELETE' });
      closeModal('#topic-modal');
      state.topics = [];
      await renderTopics();
    } catch (err) {
      alert('删除题目失败: ' + err.message);
    }
  };
}

function nextTopicNo() {
  return state.topics.reduce((m, t) => Math.max(m, Number(t.no) || 0), 0) + 1;
}

function openTaskModal(topicNo) {
  if (state.accounts.length === 0) {
    return alert('请先添加账号');
  }
  const topic = state.topics.find(t => t.no === topicNo);
  $('#task-modal-title').textContent = `#${topic.no} ${topic.title}`;
  const form = $('#task-form');
  form.topic_no.value = topicNo;
  form.account_id.innerHTML = state.accounts
    .map(a => `<option value="${a.id}">${escapeHTML(a.name)}</option>`).join('');
  form.prompt.value = '';
  form.prompt_mode.value = 'natural';
  openModal('#task-modal');

  form.onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    const body = {
      topic_no: Number(fd.get('topic_no')),
      account_id: Number(fd.get('account_id')),
      prompt: fd.get('prompt') || null,
      prompt_mode: fd.get('prompt_mode') || 'natural',
      timeout_sec: Number(fd.get('timeout_sec')),
      repeat_n: Number(fd.get('repeat_n')),
    };
    try {
      await API('/tasks', { method: 'POST', body: JSON.stringify(body) });
      closeModal('#task-modal');
      location.hash = '#tasks';
    } catch (err) { alert('创建任务失败: ' + err.message); }
  };
}

// ===================== Tasks =====================
async function renderTasks() {
  try {
    state.batches = await API('/task-batches');
    state.accounts = await API('/accounts');
    state.topics = await API('/topics');
  } catch (e) { return alert('加载任务失败: ' + e.message); }

  const accMap = Object.fromEntries(state.accounts.map(a => [a.id, a.name]));
  const form = $('#batch-form');
  if (state.accounts.length === 0) {
    form.account_id.innerHTML = '';
    $('#batch-topic-list').innerHTML = '<div class="muted">请先添加账号</div>';
    $('#batches-body').innerHTML = '<tr><td colspan="7" class="muted empty-cell">暂无账号，无法启动批次</td></tr>';
    return;
  }
  form.account_id.innerHTML = state.accounts
    .map(a => `<option value="${a.id}">${escapeHTML(a.name)}</option>`).join('');
  paintBatchTopics();

  const body = $('#batches-body');
  body.innerHTML = state.batches.map(b => `
    <tr>
      <td>${b.id}</td>
      <td>${escapeHTML(accMap[b.account_id] || `acc#${b.account_id}`)}</td>
      <td><span class="pill pill-${b.status}">${escapeHTML(b.status)}</span></td>
      <td>${b.done_count || 0}/${b.item_count || 0}</td>
      <td>${b.concurrency}</td>
      <td>${b.interval_min_sec}-${b.interval_max_sec}s</td>
      <td>${renderBatchActions(b)}</td>
    </tr>
  `).join('') || '<tr><td colspan="7" class="muted empty-cell">暂无批次</td></tr>';

  body.onclick = async (e) => {
    const pauseBatchId = e.target.dataset.pauseBatch;
    if (pauseBatchId && confirm(`暂停批次 #${pauseBatchId}? 已运行的 run 会停止，未完成项目可继续。`)) {
      e.target.disabled = true;
      try {
        await API(`/task-batches/${pauseBatchId}/pause`, { method: 'POST' });
        renderTasks();
      } catch (err) {
        alert('暂停批次失败: ' + err.message);
        e.target.disabled = false;
      }
      return;
    }
    const resumeBatchId = e.target.dataset.resumeBatch;
    if (resumeBatchId) {
      e.target.disabled = true;
      try {
        await API(`/task-batches/${resumeBatchId}/resume`, { method: 'POST' });
        renderTasks();
      } catch (err) {
        alert('继续批次失败: ' + err.message);
        e.target.disabled = false;
      }
      return;
    }
    const batchId = e.target.dataset.delBatch;
    if (batchId && confirm(`删除批次 #${batchId}?`)) {
      try {
        await API(`/task-batches/${batchId}`, { method: 'DELETE' });
        renderTasks();
      } catch (err) { alert('删除批次失败: ' + err.message); }
    }
  };

  $('#batch-select-all').onclick = () => {
    $$('#batch-topic-list input[type=checkbox]').forEach(i => { i.checked = true; });
    updateBatchSelectedCount();
  };
  $('#batch-clear-all').onclick = () => {
    $$('#batch-topic-list input[type=checkbox]').forEach(i => { i.checked = false; });
    updateBatchSelectedCount();
  };
  form.onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    const topicIds = $$('#batch-topic-list input[type=checkbox]:checked')
      .map(i => Number(i.value));
    if (topicIds.length === 0) return alert('请至少选择一个 topic');
    const body = {
      account_id: Number(fd.get('account_id')),
      topic_ids: topicIds,
      prompt: fd.get('prompt') || null,
      prompt_mode: fd.get('prompt_mode') || 'natural',
      concurrency: Number(fd.get('concurrency')),
      interval_min_sec: Number(fd.get('interval_min_sec')),
      interval_max_sec: Number(fd.get('interval_max_sec')),
      timeout_sec: Number(fd.get('timeout_sec')),
    };
    try {
      const res = await API('/task-batches', { method: 'POST', body: JSON.stringify(body) });
      alert(`已启动批次 #${res.id}`);
      location.hash = '#runs';
    } catch (err) {
      alert('启动批次失败: ' + err.message);
    }
  };
}

function paintBatchTopics() {
  const list = $('#batch-topic-list');
  list.innerHTML = state.topics.map(t => `
    <label class="batch-topic">
      <input type="checkbox" value="${t.id}" />
      <span class="topic-no">#${t.no}</span>
      <span class="batch-topic-title">${escapeHTML(t.title)}</span>
      <span class="topic-cat">${escapeHTML(t.category)}</span>
    </label>
  `).join('') || '<div class="muted">暂无 topic</div>';
  list.onchange = updateBatchSelectedCount;
  updateBatchSelectedCount();
}

function updateBatchSelectedCount() {
  const n = $$('#batch-topic-list input[type=checkbox]:checked').length;
  const el = $('#batch-selected-count');
  if (el) el.textContent = `${n} selected`;
}

function renderBatchActions(batch) {
  const pauseButton = batch.status === 'active'
    ? `<button class="btn btn-sm btn-danger" data-pause-batch="${batch.id}">暂停</button>`
    : '';
  const resumeButton = ['paused', 'stopped'].includes(batch.status)
    ? `<button class="btn btn-sm btn-primary" data-resume-batch="${batch.id}">继续</button>`
    : '';
  return `
    <div class="op-actions">
      ${pauseButton}
      ${resumeButton}
      <button class="btn btn-sm btn-danger" data-del-batch="${batch.id}">删除</button>
    </div>
  `;
}

function renderRunDetailShell(rid) {
  $('#modal-content').innerHTML = `
    <h3>Run <code>${rid}</code> <span id="run-detail-status" class="pill pill-queued">queued</span></h3>

    <div class="detail-section">
      <h4>统计</h4>
      <div class="stats-grid">
        <div class="stat-box"><div class="stat-label">输入 token</div><div class="stat-value" data-stat-key="tokens_in">等待采集</div></div>
        <div class="stat-box"><div class="stat-label">输出 token</div><div class="stat-value" data-stat-key="tokens_out">等待采集</div></div>
        <div class="stat-box"><div class="stat-label">请求数</div><div class="stat-value" data-stat-key="requests">等待采集</div></div>
        <div class="stat-box"><div class="stat-label">退出码</div><div class="stat-value" data-stat-key="exit_code">-</div></div>
        <div class="stat-box"><div class="stat-label">Claude Code</div><div class="stat-value-sm" data-stat-key="claude_code_version">-</div></div>
        <div class="stat-box"><div class="stat-label">思考预算</div><div class="stat-value-sm" data-stat-key="claude_effort_level">-</div></div>
        <div class="stat-box"><div class="stat-label">模型覆盖</div><div class="stat-value-sm" data-stat-key="model_override">默认</div></div>
      </div>
      <div class="hint inline hidden" id="run-detail-stats-error"></div>
    </div>

    <div class="detail-section">
      <h4>产物文件 (<span id="run-detail-file-count">0</span>)</h4>
      <div class="file-tree" id="run-detail-files"><div class="muted">（空）</div></div>
    </div>

    <div class="detail-section hidden" id="run-detail-capture-section">
      <h4>抓包</h4>
      <div class="capture-summary" id="run-detail-capture">等待抓包索引</div>
    </div>

    <div class="detail-section">
      <h4>Transcript</h4>
      <pre class="transcript-pre" id="run-detail-transcript">等待 transcript</pre>
    </div>

    <div class="detail-section hidden" id="run-detail-error-section">
      <h4>错误</h4>
      <pre id="run-detail-error"></pre>
    </div>
  `;
}

function setRunDetailText(selector, html) {
  const el = $(selector);
  if (el && el.innerHTML !== html) el.innerHTML = html;
}

function renderCaptureDetail(capture) {
  if (!capture || capture.error) {
    return `<div class="muted">${escapeHTML(capture?.error || '等待抓包索引')}</div>`;
  }
  const index = capture.index || {};
  const entries = Array.isArray(index.entries) ? index.entries : [];
  const files = Array.isArray(capture.files) ? capture.files : [];
  const versions = Array.isArray(index.cc_versions) ? index.cc_versions : [];
  const entryRows = entries.slice(-8).map(e => {
    const req = e.request || {};
    const resp = e.response || {};
    const ana = e.analysis || {};
    const path = `${req.method || '-'} ${req.host || '-'}${req.path || ''}`;
    return `
      <tr>
        <td><code>${escapeHTML(e.flow_id || '-')}</code></td>
        <td>${escapeHTML(path)}</td>
        <td>${escapeHTML(resp.status ?? '-')}</td>
        <td>${escapeHTML(req.body_bytes ?? 0)} / ${escapeHTML(resp.body_bytes ?? 0)}</td>
        <td>${escapeHTML(ana.cc_version || '-')}</td>
      </tr>
    `;
  }).join('');
  const fileRows = files.map(f => `
    <div class="file">${escapeHTML(f.path)}<span class="size">${formatSize(f.size || 0)}</span></div>
  `).join('') || '<div class="muted">暂无抓包文件</div>';
  const captureStats = `
    <div class="stats-grid capture-stats">
      <div class="stat-box"><div class="stat-label">flows</div><div class="stat-value">${escapeHTML(index.total_flows ?? entries.length)}</div></div>
      <div class="stat-box"><div class="stat-label">运行版本</div><div class="stat-value-sm">${escapeHTML(capture.claude_code_version || '-')}</div></div>
      <div class="stat-box"><div class="stat-label">思考预算</div><div class="stat-value-sm">${escapeHTML(capture.claude_effort_level || '-')}</div></div>
      <div class="stat-box"><div class="stat-label">cc_version</div><div class="stat-value-sm">${versions.length ? versions.map(escapeHTML).join('<br>') : '<span class="muted">未观察到</span>'}</div></div>
      <div class="stat-box"><div class="stat-label">模式</div><div class="stat-value-sm">${escapeHTML(capture.mode || 'full_http')}</div></div>
      <div class="stat-box"><div class="stat-label">model</div><div class="stat-value-sm">${capture.model_override ? escapeHTML(capture.model_override) : '<span class="muted">默认</span>'}</div></div>
    </div>
  `;
  if (capture.available === false) {
    return `
      ${captureStats}
      <div class="muted">${escapeHTML(index.error || '等待抓包索引')}</div>
      <div class="file-tree capture-files">${fileRows}</div>
    `;
  }
  return `
    ${captureStats}
    <div class="hint inline">完整请求体和响应体保存在 flows 目录；此处只展示脱敏索引。</div>
    <div class="file-tree capture-files">${fileRows}</div>
    <table class="data capture-table">
      <thead><tr><th>flow</th><th>请求</th><th>状态</th><th>请求/响应字节</th><th>cc_version</th></tr></thead>
      <tbody>${entryRows || '<tr><td colspan="5" class="muted empty-cell">暂无目标请求</td></tr>'}</tbody>
    </table>
  `;
}

function updateRunDetailContent(rid, run, files, stats, transcript, transcriptState, capture) {
  const detail = state.runDetail;
  if (!detail?.rendered) renderRunDetailShell(rid);
  const safeStatus = escapeHTML(run.status);

  const statusEl = $('#run-detail-status');
  if (statusEl) {
    const nextClass = `pill pill-${safeStatus}`;
    if (statusEl.className !== nextClass) statusEl.className = nextClass;
    if (statusEl.textContent !== run.status) statusEl.textContent = run.status;
  }

  setRunDetailText('[data-stat-key="tokens_in"]', renderStatValue(stats, 'tokens_in'));
  setRunDetailText('[data-stat-key="tokens_out"]', renderStatValue(stats, 'tokens_out'));
  setRunDetailText('[data-stat-key="requests"]', renderStatValue(stats, 'requests'));
  setRunDetailText('[data-stat-key="exit_code"]', escapeHTML(run.exit_code ?? '-'));
  setRunDetailText('[data-stat-key="claude_code_version"]', escapeHTML(run.claude_code_version || '-'));
  setRunDetailText('[data-stat-key="claude_effort_level"]', escapeHTML(run.claude_effort_level || '-'));
  setRunDetailText('[data-stat-key="model_override"]', run.capture_model_override ? escapeHTML(run.capture_model_override) : '<span class="muted">默认</span>');

  const statsError = $('#run-detail-stats-error');
  if (statsError) {
    statsError.classList.toggle('hidden', !stats?.error);
    statsError.textContent = stats?.error ? `统计加载失败：${stats.error}` : '';
  }

  const filesHTML = files.length ? files.map(f => `
    <div class="${escapeHTML(f.type)}">${escapeHTML(f.path)}${f.size != null ? `<span class="size">${formatSize(f.size)}</span>` : ''}</div>
  `).join('') : '<div class="muted">（空）</div>';
  if (detail.lastFilesHTML !== filesHTML) {
    detail.lastFilesHTML = filesHTML;
    setRunDetailText('#run-detail-file-count', escapeHTML(files.length));
    setRunDetailText('#run-detail-files', filesHTML);
  }

  const captureSection = $('#run-detail-capture-section');
  if (captureSection) {
    const isCapture = (run.run_kind || 'normal') === 'capture';
    captureSection.classList.toggle('hidden', !isCapture);
    if (isCapture) {
      const captureHTML = renderCaptureDetail(capture);
      if (detail.lastCaptureHTML !== captureHTML) {
        detail.lastCaptureHTML = captureHTML;
        setRunDetailText('#run-detail-capture', captureHTML);
      }
    }
  }

  const transcriptText = transcript || transcriptState || '等待 transcript';
  if (detail.lastTranscript !== transcriptText) {
    detail.lastTranscript = transcriptText;
    const pre = $('#run-detail-transcript');
    if (pre) pre.textContent = transcriptText;
  }

  const errorSection = $('#run-detail-error-section');
  const errorPre = $('#run-detail-error');
  if (errorSection && errorPre) {
    errorSection.classList.toggle('hidden', !run.error);
    if (run.error && errorPre.textContent !== run.error) errorPre.textContent = run.error;
  }
  detail.rendered = true;
}

// ===================== Runs (SSE 实时) =====================
async function renderRuns() {
  try {
    state.accounts = await API('/accounts');
    state.tasks = await API('/tasks');
    state.topics = await API('/topics');
    state.runtimeModel = await API('/settings/runtime-model');
    state.runtimeEffort = await API('/settings/runtime-effort');
    state.claudeCodeVersion = await API('/settings/claude-code-version');
  } catch (e) {
    return alert('加载运行依赖失败: ' + e.message);
  }
  bindRuntimeModelForm();
  bindRuntimeEffortForm();
  bindClaudeCodeVersionForm();
  bindCaptureForm();
  paintRuns(state.runs);
  if (state.runsEventSource) state.runsEventSource.close();
  state.runsEventSource = new EventSource('/api/runs-stream');
  state.runsEventSource.addEventListener('runs', (e) => {
    try {
      state.runs = JSON.parse(e.data);
      paintRuns(state.runs);
    } catch {}
  });
  // 首次也拉一下
  API('/runs').then(rs => { state.runs = rs; paintRuns(rs); }).catch(() => {});
}

function paintRuntimeModelSetting() {
  const form = $('#runtime-model-form');
  if (!form || !state.runtimeModel) return;
  const configured = state.runtimeModel.configured_model;
  const effective = state.runtimeModel.effective_model || state.runtimeModel.env_default_model || '-';
  form.default_model.value = configured || '';
  $('#runtime-model-effective').textContent = effective;
  $('#runtime-model-source').innerHTML = configured
    ? `页面覆盖；.env 兜底为 <code>${escapeHTML(state.runtimeModel.env_default_model || '-')}</code>`
    : `.env 兜底：<code>${escapeHTML(state.runtimeModel.env_default_model || '-')}</code>`;
}

function bindRuntimeModelForm() {
  const form = $('#runtime-model-form');
  if (!form) return;
  paintRuntimeModelSetting();
  const resetBtn = $('#runtime-model-reset');
  if (resetBtn) {
    resetBtn.onclick = () => {
      form.default_model.value = '';
      form.requestSubmit();
    };
  }
  form.onsubmit = async (e) => {
    e.preventDefault();
    const btn = form.querySelector('button[type=submit]');
    const body = {
      default_model: (new FormData(form).get('default_model') || '').trim() || null,
    };
    btn.disabled = true;
    if (resetBtn) resetBtn.disabled = true;
    try {
      state.runtimeModel = await API('/settings/runtime-model', {
        method: 'PUT',
        body: JSON.stringify(body),
      });
      paintRuntimeModelSetting();
    } catch (err) {
      alert('保存默认模型失败: ' + err.message);
    } finally {
      btn.disabled = false;
      if (resetBtn) resetBtn.disabled = false;
    }
  };
}

function paintRuntimeEffortSetting() {
  const form = $('#runtime-effort-form');
  if (!form || !state.runtimeEffort) return;
  const configured = state.runtimeEffort.configured_effort;
  const effective = state.runtimeEffort.effective_effort || state.runtimeEffort.env_default_effort || '-';
  const allowed = state.runtimeEffort.allowed_efforts || [];
  form.effort_level.innerHTML = [
    `<option value="">回退 .env (${escapeHTML(state.runtimeEffort.env_default_effort || '-')})</option>`,
    ...allowed.map(v => `<option value="${escapeHTML(v)}">${escapeHTML(v)}</option>`),
  ].join('');
  form.effort_level.value = configured || '';
  $('#runtime-effort-effective').textContent = effective;
  $('#runtime-effort-source').innerHTML = configured
    ? `页面覆盖；.env 兜底为 <code>${escapeHTML(state.runtimeEffort.env_default_effort || '-')}</code>`
    : `.env 兜底：<code>${escapeHTML(state.runtimeEffort.env_default_effort || '-')}</code>`;
}

function bindRuntimeEffortForm() {
  const form = $('#runtime-effort-form');
  if (!form) return;
  paintRuntimeEffortSetting();
  const resetBtn = $('#runtime-effort-reset');
  if (resetBtn) {
    resetBtn.onclick = () => {
      form.effort_level.value = '';
      form.requestSubmit();
    };
  }
  form.onsubmit = async (e) => {
    e.preventDefault();
    const btn = form.querySelector('button[type=submit]');
    const body = {
      effort_level: (new FormData(form).get('effort_level') || '').trim() || null,
    };
    btn.disabled = true;
    if (resetBtn) resetBtn.disabled = true;
    try {
      state.runtimeEffort = await API('/settings/runtime-effort', {
        method: 'PUT',
        body: JSON.stringify(body),
      });
      paintRuntimeEffortSetting();
    } catch (err) {
      alert('保存思考预算失败: ' + err.message);
    } finally {
      btn.disabled = false;
      if (resetBtn) resetBtn.disabled = false;
    }
  };
}

function paintClaudeCodeVersionSetting() {
  const form = $('#claude-code-version-form');
  if (!form || !state.claudeCodeVersion) return;
  const configured = state.claudeCodeVersion.configured_version;
  const effective = state.claudeCodeVersion.effective_version || state.claudeCodeVersion.env_default_version || '-';
  form.claude_code_version.value = configured || '';
  $('#claude-code-version-effective').textContent = effective;
  $('#claude-code-version-source').innerHTML = configured
    ? `页面覆盖；.env 兜底为 <code>${escapeHTML(state.claudeCodeVersion.env_default_version || '-')}</code>`
    : `.env 兜底：<code>${escapeHTML(state.claudeCodeVersion.env_default_version || '-')}</code>`;
}

function bindClaudeCodeVersionForm() {
  const form = $('#claude-code-version-form');
  if (!form) return;
  paintClaudeCodeVersionSetting();
  const resetBtn = $('#claude-code-version-reset');
  if (resetBtn) {
    resetBtn.onclick = () => {
      form.claude_code_version.value = '';
      form.requestSubmit();
    };
  }
  form.onsubmit = async (e) => {
    e.preventDefault();
    const btn = form.querySelector('button[type=submit]');
    const body = {
      claude_code_version: (new FormData(form).get('claude_code_version') || '').trim() || null,
    };
    btn.disabled = true;
    if (resetBtn) resetBtn.disabled = true;
    try {
      state.claudeCodeVersion = await API('/settings/claude-code-version', {
        method: 'PUT',
        body: JSON.stringify(body),
      });
      paintClaudeCodeVersionSetting();
    } catch (err) {
      alert('保存 Claude Code 版本失败: ' + err.message);
    } finally {
      btn.disabled = false;
      if (resetBtn) resetBtn.disabled = false;
    }
  };
}

function bindCaptureForm() {
  const form = $('#capture-form');
  if (!form) return;
  form.account_id.innerHTML = state.accounts
    .map(a => `<option value="${a.id}">${escapeHTML(a.name)}</option>`).join('');
  form.topic_id.innerHTML = state.topics
    .map(t => `<option value="${t.id}">#${t.no} ${escapeHTML(t.title)}</option>`).join('');
  const effortSetting = state.runtimeEffort || {};
  form.effort_level.innerHTML = [
    `<option value="">默认 .env (${escapeHTML(effortSetting.env_default_effort || '-')})</option>`,
    ...(effortSetting.allowed_efforts || [])
      .map(v => `<option value="${escapeHTML(v)}">${escapeHTML(v)}</option>`),
  ].join('');
  form.effort_level.value = '';
  form.onsubmit = async (e) => {
    e.preventDefault();
    if (state.accounts.length === 0) return alert('请先添加账号');
    if (state.topics.length === 0) return alert('请先添加题目');
    const btn = form.querySelector('button[type=submit]');
    const fd = new FormData(form);
    const body = {
      account_id: Number(fd.get('account_id')),
      topic_id: Number(fd.get('topic_id')),
      timeout_sec: Number(fd.get('timeout_sec')),
      prompt: fd.get('prompt') || null,
      prompt_mode: fd.get('prompt_mode') || 'canonical',
      model_override: (fd.get('model_override') || '').trim() || null,
      effort_level: (fd.get('effort_level') || '').trim() || null,
    };
    btn.disabled = true;
    try {
      const res = await API('/captures/run', {
        method: 'POST',
        body: JSON.stringify(body),
      });
      form.prompt.value = '';
      form.model_override.value = '';
      form.effort_level.value = '';
      await Promise.all([
        API('/tasks').then(ts => { state.tasks = ts; }),
        API('/runs').then(rs => { state.runs = rs; }),
      ]).catch(() => {});
      paintRuns(state.runs);
      openRunDetail(res.run_id);
    } catch (err) {
      alert('启动抓包失败: ' + err.message);
    } finally {
      btn.disabled = false;
    }
  };
}

function paintRuns(runs) {
  const body = $('#runs-body');
  if (!body) return;
  const accMap = Object.fromEntries(state.accounts.map(a => [a.id, a.name]));
  const taskMap = Object.fromEntries(state.tasks.map(t => [t.id, t]));
  body.innerHTML = runs.map(r => {
    const task = taskMap[r.task_id];
    const tname = task ? `#${task.topic_no} ${escapeHTML(task.title)}` : `task#${r.task_id}`;
    const runKind = r.run_kind || 'normal';
    const kind = runKind === 'capture'
      ? ' <span class="pill pill-capture">抓包</span>'
      : (runKind === 'warmup' ? ' <span class="pill pill-warmup">养号</span>' : '');
    const dur = (r.started_at && r.ended_at) ? `${(r.ended_at - r.started_at).toFixed(0)}s` :
                (r.started_at ? `${(Date.now()/1000 - r.started_at).toFixed(0)}s` : '-');
    const terminal = ['success', 'failed', 'timeout', 'stopped', 'auth_failed'].includes(r.status);
    return `
      <tr>
        <td><code>${r.id}</code></td>
        <td>${tname}${kind}</td>
        <td>${escapeHTML(accMap[r.account_id] || `acc#${r.account_id}`)}</td>
        <td><span class="pill pill-${r.status}">${escapeHTML(r.status)}</span></td>
        <td>${dur}</td>
        <td>${r.exit_code ?? '-'}</td>
        <td><div class="op-actions run-actions">
          <button class="btn btn-sm" data-detail="${r.id}">详情</button>
          ${['queued', 'running'].includes(r.status) ? `<button class="btn btn-sm btn-danger" data-stop="${r.id}">停止</button>` : ''}
          ${terminal ? `<button class="btn btn-sm btn-primary" data-continue="${r.id}">继续</button>` : ''}
          ${terminal ? `<button class="btn btn-sm btn-danger" data-del-run="${r.id}">删除</button>` : ''}
        </div></td>
      </tr>
    `;
  }).join('') || '<tr><td colspan="7" class="muted empty-cell">暂无运行</td></tr>';

  body.onclick = async (e) => {
    const rid = e.target.dataset.detail;
    if (rid) openRunDetail(rid);
    const stopId = e.target.dataset.stop;
    if (stopId && confirm(`停止 run ${stopId}?`)) {
      e.target.disabled = true;
      try { await API(`/runs/${stopId}/stop`, { method: 'POST' }); }
      catch (err) { alert('停止失败: ' + err.message); e.target.disabled = false; }
      return;
    }
    const contId = e.target.dataset.continue;
    if (contId) {
      e.target.disabled = true;
      try { await startContinueRun(contId); }
      catch (err) { alert('继续对话失败: ' + err.message); }
      finally { e.target.disabled = false; }
      return;
    }
    const delId = e.target.dataset.delRun;
    if (delId && confirm(`删除 run ${delId}?`)) {
      try { await API(`/runs/${delId}`, { method: 'DELETE' }); }
      catch (err) { alert('删除运行失败: ' + err.message); }
    }
  };
}

function isLiveRunStatus(status) {
  return ['queued', 'running', 'stopping'].includes(status);
}

function endRunDetail() {
  const detail = state.runDetail;
  if (detail && detail.timer) clearTimeout(detail.timer);
  state.runDetail = null;
}

function renderStatValue(stats, key) {
  if (stats?.error) return '<span class="stat-waiting">加载失败</span>';
  if (!stats || stats.available === false) return '<span class="stat-waiting">等待采集</span>';
  if ((key === 'tokens_in' || key === 'tokens_out') && stats.usage_available === false) {
    return '<span class="stat-waiting">等待采集</span>';
  }
  return escapeHTML(stats[key] ?? 0);
}

async function fetchRunTranscript(rid) {
  try {
    const r = await fetch(`/api/runs/${rid}/transcript`, { credentials: 'same-origin' });
    if (r.status === 404) return { text: '', state: '等待 transcript' };
    if (!r.ok) return { text: '', state: `transcript 加载失败：${r.status} ${r.statusText}` };
    return { text: await r.text(), state: '' };
  } catch (e) {
    return { text: '', state: `transcript 加载失败：${e.message}` };
  }
}

async function refreshRunDetail() {
  const detail = state.runDetail;
  if (!detail) return;
  const seq = ++detail.seq;
  const rid = detail.rid;
  try {
    const shouldRefreshFiles = detail.files == null || detail.fileRefreshDue || detail.finalFilesPending;
    const [run, statsResult, transcriptResult, filesResult] = await Promise.all([
      API(`/runs/${rid}`),
      API(`/runs/${rid}/stats`).catch(e => ({ error: e.message })),
      fetchRunTranscript(rid),
      shouldRefreshFiles ? API(`/runs/${rid}/files`).catch(() => detail.files || []) : Promise.resolve(detail.files || []),
    ]);
    if (!state.runDetail || state.runDetail.rid !== rid || state.runDetail.seq !== seq) return;

    detail.files = filesResult;
    if (shouldRefreshFiles) detail.lastFileRefreshAt = Date.now();
    detail.fileRefreshDue = false;
    let captureResult = detail.capture || null;
    if ((run.run_kind || 'normal') === 'capture') {
      captureResult = await API(`/runs/${rid}/capture`).catch(e => ({ error: e.message }));
      if (!state.runDetail || state.runDetail.rid !== rid || state.runDetail.seq !== seq) return;
      detail.capture = captureResult;
    }
    updateRunDetailContent(
      rid,
      run,
      detail.files,
      statsResult,
      transcriptResult.text,
      transcriptResult.state,
      captureResult,
    );

    if (isLiveRunStatus(run.status)) {
      detail.fileRefreshDue = Date.now() - detail.lastFileRefreshAt > 10000;
      detail.timer = setTimeout(refreshRunDetail, 2500);
    } else if (detail.finalFilesPending) {
      detail.finalFilesPending = false;
      detail.fileRefreshDue = true;
      detail.timer = setTimeout(refreshRunDetail, 200);
    } else {
      detail.timer = null;
    }
  } catch (e) {
    if (!state.runDetail || state.runDetail.rid !== rid || state.runDetail.seq !== seq) return;
    if (!detail.rendered) $('#modal-content').innerHTML = `<p>加载失败: ${escapeHTML(e.message)}</p>`;
    detail.timer = setTimeout(refreshRunDetail, 2500);
  }
}

async function openRunDetail(rid) {
  endRunDetail();
  state.runDetail = {
    rid,
    timer: null,
    seq: 0,
    files: null,
    fileRefreshDue: true,
    finalFilesPending: true,
    lastFileRefreshAt: 0,
    rendered: false,
    lastFilesHTML: '',
    lastTranscript: '',
    lastCaptureHTML: '',
    capture: null,
  };
  $('#modal-content').innerHTML = '<p class="muted">加载中…</p>';
  openModal('#modal');
  refreshRunDetail();
}

async function startContinueRun(rid) {
  const resp = await API(`/runs/${rid}/continue/start`, { method: 'POST' });
  state.continueRun = {
    sid: resp.session_id,
    runId: rid,
  };
  $('#continue-run-id').textContent = rid;
  $('#continue-session-id').textContent = resp.claude_session_id || '-';
  $('#continue-modal-title').textContent = rid;
  openModal('#continue-modal');
  const termState = await attachTerminal('#continue-xterm', resp.ws_path);
  state.continueRun.term = termState.term;
  state.continueRun.fit = termState.fit;
  state.continueRun.ws = termState.ws;
  state.continueRun.onResize = termState.onResize;
}

function endContinueRun({ alsoCloseModal = false } = {}) {
  const cr = state.continueRun || {};
  if (cr.ws && cr.ws.readyState <= 1) {
    try { cr.ws.close(); } catch {}
  }
  if (cr.term) { try { cr.term.dispose(); } catch {} }
  if (cr.onResize) window.removeEventListener('resize', cr.onResize);
  if (cr.sid) {
    API(`/run-continue/${cr.sid}`, { method: 'DELETE' }).catch(() => {});
  }
  state.continueRun = null;
  if (alsoCloseModal) closeModal('#continue-modal');
}

// ===================== Modal helpers =====================
function openModal(sel) { $(sel).classList.remove('hidden'); }
function closeModal(sel) { $(sel).classList.add('hidden'); }

document.addEventListener('click', (e) => {
  if (e.target.id === 'modal-close' || e.target.matches('[data-close]')) {
    const sel = e.target.dataset.close || '#modal';
    // acc-modal 关闭走 endAccLogin（同时清服务端 session 容器；无 session 时幂等）
    if (sel === '#acc-modal' && typeof endAccLogin === 'function') {
      return endAccLogin({ alsoCloseModal: true });
    }
    if (sel === '#continue-modal' && typeof endContinueRun === 'function') {
      return endContinueRun({ alsoCloseModal: true });
    }
    if (sel === '#modal') endRunDetail();
    closeModal(sel);
  }
  if (e.target.classList && e.target.classList.contains('modal')) {
    const id = '#' + e.target.id;
    if (id === '#acc-modal' && typeof endAccLogin === 'function') {
      return endAccLogin({ alsoCloseModal: true });
    }
    if (id === '#continue-modal' && typeof endContinueRun === 'function') {
      return endContinueRun({ alsoCloseModal: true });
    }
    if (id === '#modal') endRunDetail();
    closeModal(id);
  }
});

// ===================== utils =====================
function escapeHTML(s) {
  if (s == null) return '';
  return String(s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}

function formatSize(n) {
  if (n < 1024) return n + ' B';
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
  return (n / 1024 / 1024).toFixed(1) + ' MB';
}

// ===================== chrome (theme + clock + shortcuts) =====================
function setupTheme() {
  const btn = document.getElementById('theme-toggle');
  if (!btn) return;
  const root = document.documentElement;
  const updateBtn = () => {
    const cur = root.dataset.theme || 'dark';
    btn.textContent = cur === 'light' ? '☾' : '☀';
    btn.title = cur === 'light' ? 'switch to dark' : 'switch to light';
  };
  updateBtn();           // 初始图标（主题已在 <head> 防 FOUC 脚本里就位）
  btn.onclick = () => {
    const next = (root.dataset.theme === 'light') ? 'dark' : 'light';
    root.dataset.theme = next;
    try { localStorage.setItem('vibebench-theme', next); } catch {}
    updateBtn();
  };
}


function startClock() {
  const el = document.getElementById('clock');
  if (!el) return;
  const pad = (n) => String(n).padStart(2, '0');
  const tick = () => {
    const d = new Date();
    el.textContent = `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  };
  tick();
  setInterval(tick, 1000);
}

function bindShortcuts() {
  const TAB_KEYS = { '1': 'accounts', '2': 'topics', '3': 'tasks', '4': 'runs' };
  document.addEventListener('keydown', (e) => {
    const inField = /^(INPUT|TEXTAREA|SELECT)$/i.test(e.target.tagName);

    // Esc: close any open modal —— 但 data-no-esc 的模态框(如登录框)免疫
    if (e.key === 'Escape') {
      $$('.modal:not(.hidden)').forEach((m) => {
        if (m.hasAttribute('data-no-esc')) return;
        if (m.id === 'acc-modal' && typeof endAccLogin === 'function') {
          endAccLogin({ alsoCloseModal: true });
        } else if (m.id === 'continue-modal' && typeof endContinueRun === 'function') {
          endContinueRun({ alsoCloseModal: true });
        } else {
          if (m.id === 'modal') endRunDetail();
          closeModal('#' + m.id);
        }
      });
      return;
    }

    if (inField) return;     // 后续快捷键在输入框中不响应

    // 登录框未关之前 1-4/'/' 都不导航(防止键盘漏到底层 tab)
    if ($('#auth-modal') && !$('#auth-modal').classList.contains('hidden')) return;

    // '/': focus topic filter (auto-switch to topics tab if not there)
    if (e.key === '/') {
      e.preventDefault();
      if (currentTab() !== 'topics') location.hash = '#topics';
      setTimeout(() => { const f = $('#topic-filter'); if (f) f.focus(); }, 60);
      return;
    }

    // 1..4: tabs
    if (TAB_KEYS[e.key]) {
      e.preventDefault();
      location.hash = '#' + TAB_KEYS[e.key];
    }
  });
}

// ===================== Auth (cookie session) =====================
function showAuthModal() {
  const m = $('#auth-modal');
  if (!m) return;
  m.classList.remove('hidden');
  // 清错 + 聚焦,延后到 DOM 已 layout
  $('#auth-error')?.classList.add('hidden');
  setTimeout(() => $('#auth-modal input[name=user]')?.focus(), 30);
}

function hideAuthModal() {
  $('#auth-modal')?.classList.add('hidden');
}

function showAuthUser(user) {
  if (!user) return;
  const pill = $('#auth-pill');
  if (!pill) return;
  $('#auth-user').textContent = user;
  pill.classList.remove('hidden');
  $('.auth-pill-sep')?.classList.remove('hidden');
}

function hideAuthUser() {
  $('#auth-pill')?.classList.add('hidden');
  $('.auth-pill-sep')?.classList.add('hidden');
}

/**
 * 启动时探测鉴权状态:
 *   - 后端 auth 未启用 → auth_required=false,无登录态概念,正常渲染
 *   - 后端 auth 启用 + 已登录 → 显示用户 pill,正常渲染
 *   - 后端 auth 启用 + 未登录 → 401,弹登录框
 */
async function bootstrapAuth() {
  try {
    const r = await fetch('/api/auth/me', { credentials: 'same-origin' });
    if (r.status === 401) { showAuthModal(); return false; }
    if (!r.ok) return true;   // 其他错(如后端没起)不阻塞 UI
    const data = await r.json();
    if (data.auth_required && data.user) showAuthUser(data.user);
    return true;
  } catch (e) {
    return true;   // 网络层错不阻塞,后续 API 会再触发
  }
}

function wireAuth() {
  const form = $('#auth-form');
  if (form) {
    form.onsubmit = async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const errEl = $('#auth-error');
      const btn = $('#auth-submit');
      errEl?.classList.add('hidden');
      btn.disabled = true;
      try {
        const r = await fetch('/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'same-origin',
          body: JSON.stringify({ user: fd.get('user'), pwd: fd.get('pwd') }),
        });
        if (!r.ok) {
          let detail = `${r.status} ${r.statusText}`;
          try { const j = await r.json(); detail = j.detail || detail; } catch {}
          errEl.textContent = `! ${detail}`;
          errEl.classList.remove('hidden');
          $('#auth-modal input[name=pwd]').select();
          return;
        }
        const data = await r.json();
        hideAuthModal();
        showAuthUser(data.user);
        form.reset();
        // 登录成功后重渲染当前页(拉真实数据)
        navigate();
      } catch (err) {
        errEl.textContent = `! network: ${err.message}`;
        errEl.classList.remove('hidden');
      } finally {
        btn.disabled = false;
      }
    };
  }

  const logoutBtn = $('#auth-logout');
  if (logoutBtn) {
    logoutBtn.onclick = async (e) => {
      e.stopPropagation();
      if (!confirm('退出登录?')) return;
      try {
        await fetch('/api/auth/logout', { method: 'POST', credentials: 'same-origin' });
      } catch {}
      hideAuthUser();
      location.reload();
    };
  }
}

// ===================== 启动 =====================
(async () => {
  wireAuth();
  setupTheme();
  startClock();
  bindShortcuts();
  const ok = await bootstrapAuth();
  // ok=true 时(已登录 或 后端未启用 auth)才渲染;未登录时只显示登录框,
  // 避免立刻调 /api/accounts 拉数据触发一连串 401 + alert
  if (ok) navigate();
}) ();
