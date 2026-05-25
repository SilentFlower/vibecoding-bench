/**
 * vibecoding-100 bench WebUI
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
  topics: [],
  tasks: [],
  runs: [],
  topicFilter: '',
  runsEventSource: null,
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
  ROUTES[tab]();
}

window.addEventListener('hashchange', navigate);

// ===================== Accounts =====================
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
      <td>${a.upstream_socks5_host ? `${escapeHTML(a.upstream_socks5_host)}:${a.upstream_socks5_port || ''}` : '<span class="muted">未配置</span>'}</td>
      <td>${a.enabled ? '✓' : '✗'}</td>
      <td><button class="btn btn-sm btn-danger" data-del="${a.id}">删除</button></td>
    </tr>
  `).join('') || '<tr><td colspan="6" class="muted" style="text-align:center;padding:24px">暂无账号</td></tr>';

  body.onclick = async (e) => {
    const id = e.target.dataset.del;
    if (id && confirm(`删除账号 #${id}?`)) {
      await API(`/accounts/${id}`, { method: 'DELETE' });
      renderAccounts();
    }
  };

  $('#add-account').onclick = () => openAccLoginModal();
  $('#acc-form').onsubmit = (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const body = {};
    for (const [k, v] of fd) if (v) body[k] = k.endsWith('_port') ? Number(v) : v;
    startAccLogin(body);
  };
  // SOCKS5 URL 粘贴解析:输入即触发,实时回填下面 4 个字段
  const urlInput = $('#acc-socks5-url');
  if (urlInput) {
    urlInput.addEventListener('input', () => applySocks5Url(urlInput.value));
  }
  $('#acc-login-cancel').onclick = () => endAccLogin({ alsoCloseModal: true });
  $('#acc-login-commit').onclick = () => commitAccLogin();
  $('#acc-modal-close').onclick = () => endAccLogin({ alsoCloseModal: true });
}

/**
 * 解析 socks5 / socks5h URL,成功则回填 acc-form 的 4 个字段。
 * 支持格式:
 *   socks5://user:pass@host:port
 *   socks5h://user:pass@host:port
 *   socks5://host:port            (无凭据)
 *   socks5://user:pass@host       (省略端口 → 1080)
 * 失败静默不动 — 让用户手填或继续粘贴。
 */
function parseSocks5Url(s) {
  if (!s) return null;
  const m = String(s).trim().match(
    /^socks5h?:\/\/(?:([^:@\s]+)(?::([^@\s]+))?@)?([^:/\s@]+)(?::(\d+))?\/?$/i
  );
  if (!m) return null;
  return {
    user: m[1] ? decodeURIComponent(m[1]) : '',
    pass: m[2] ? decodeURIComponent(m[2]) : '',
    host: m[3],
    port: m[4] ? Number(m[4]) : 1080,
  };
}

function applySocks5Url(raw) {
  const parsed = parseSocks5Url(raw);
  if (!parsed) return false;
  const form = $('#acc-form');
  if (!form) return false;
  form.elements['upstream_socks5_host'].value = parsed.host;
  form.elements['upstream_socks5_port'].value = String(parsed.port);
  form.elements['upstream_socks5_user'].value = parsed.user;
  form.elements['upstream_socks5_pass'].value = parsed.pass;
  return true;
}

// ============== OAuth 登录两步流（acc-modal） ==============
// 流程：
//   step 1: 用户填 name + socks5 → POST /api/accounts/login/start → 拿 session_id
//   step 2: 打开 WS PTY → 用户在 xterm 里走 claude auth login → 点 commit
//   commit: POST /api/accounts/login/{sid}/commit → 校验 → 写库 → 关容器
// 取消任意一步都 DELETE /api/accounts/login/{sid} 清场。
function openAccLoginModal() {
  // 重置到 step 1
  showAccStep('config');
  $('#acc-form').reset();
  $('#acc-modal-stage').textContent = 'step 1 · configure';
  openModal('#acc-modal');
}

function showAccStep(which) {
  // which = 'config' | 'terminal'
  $('.acc-step-config').classList.toggle('hidden', which !== 'config');
  $('.acc-step-terminal').classList.toggle('hidden', which !== 'terminal');
}

async function startAccLogin(body) {
  state.accLogin = state.accLogin || {};
  let resp;
  try {
    resp = await API('/accounts/login/start', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  } catch (e) {
    return alert('启动登录会话失败: ' + e.message);
  }
  // 保存 socks5/name 给 commit 用
  state.accLogin.body = body;
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
  // 等 xterm.js 全部加载
  if (typeof Terminal === 'undefined') {
    await new Promise(r => {
      const t = setInterval(() => {
        if (typeof Terminal !== 'undefined' && typeof FitAddon !== 'undefined') {
          clearInterval(t); r();
        }
      }, 50);
    });
  }

  const host = $('#acc-login-xterm');
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

  state.accLogin.term = term;
  state.accLogin.fit = fit;
  state.accLogin.ws = ws;

  ws.onopen = () => {
    // 通知后端当前终端尺寸
    ws.send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }));
    term.focus();
  };
  ws.onmessage = (e) => {
    if (e.data instanceof ArrayBuffer) {
      term.write(new Uint8Array(e.data));
    } else if (typeof e.data === 'string') {
      // 服务器偶尔发文本（错误信息），统一渲染
      try {
        const msg = JSON.parse(e.data);
        if (msg.type === 'error') term.write(`\r\n\x1b[31m[orchestrator] ${msg.msg}\x1b[0m\r\n`);
      } catch { term.write(e.data); }
    }
  };
  ws.onclose = () => {
    term.write('\r\n\x1b[90m[ws closed]\x1b[0m\r\n');
  };
  ws.onerror = (e) => {
    term.write(`\r\n\x1b[31m[ws error]\x1b[0m\r\n`);
  };

  // 把用户键盘输入透传给后端
  term.onData((data) => {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'input', data }));
    }
  });

  // 窗口变化重新 fit + 通知后端
  const onResize = () => {
    try { fit.fit(); } catch {}
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }));
    }
  };
  window.addEventListener('resize', onResize);
  state.accLogin.onResize = onResize;
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
    if (al.term) al.term.write(`\r\n\x1b[32m[ok] account saved (#${r.id}) · auth=${r.auth_method}\x1b[0m\r\n`);
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
  state.accounts = await API('/accounts');

  $('#topics-count').textContent = `(${state.topics.length})`;
  const list = $('#topics-list');
  const filter = state.topicFilter.toLowerCase();

  list.innerHTML = state.topics
    .filter(t => !filter ||
      t.title.toLowerCase().includes(filter) ||
      t.category.toLowerCase().includes(filter) ||
      String(t.no).includes(filter))
    .map(t => `
      <div class="topic-card" data-no="${t.no}">
        <div class="topic-no">#${t.no}</div>
        <div class="topic-title">${escapeHTML(t.title)}</div>
        <div class="topic-desc">${escapeHTML(t.description)}</div>
        <div class="topic-cat">${escapeHTML(t.category)}</div>
      </div>
    `).join('');

  list.onclick = (e) => {
    const card = e.target.closest('.topic-card');
    if (!card) return;
    openTaskModal(Number(card.dataset.no));
  };

  $('#topic-filter').oninput = (e) => {
    state.topicFilter = e.target.value;
    renderTopics();
  };
  $('#topic-filter').value = state.topicFilter;
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
  openModal('#task-modal');

  form.onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    const body = {
      topic_no: Number(fd.get('topic_no')),
      account_id: Number(fd.get('account_id')),
      prompt: fd.get('prompt') || null,
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
    state.tasks = await API('/tasks');
    state.accounts = await API('/accounts');
  } catch (e) { return alert('加载任务失败: ' + e.message); }

  const accMap = Object.fromEntries(state.accounts.map(a => [a.id, a.name]));
  const body = $('#tasks-body');
  body.innerHTML = state.tasks.map(t => `
    <tr>
      <td>${t.id}</td>
      <td>#${t.topic_no}</td>
      <td>${escapeHTML(t.title)}</td>
      <td>${escapeHTML(accMap[t.account_id] || `acc#${t.account_id}`)}</td>
      <td>${t.repeat_n}</td>
      <td>${t.timeout_sec}s</td>
      <td>
        <button class="btn btn-sm btn-primary" data-run="${t.id}">▶ 运行</button>
      </td>
    </tr>
  `).join('') || '<tr><td colspan="7" class="muted" style="text-align:center;padding:24px">暂无任务，去 <a href="#topics">题库</a> 选题</td></tr>';

  body.onclick = async (e) => {
    const tid = e.target.dataset.run;
    if (tid) {
      e.target.disabled = true;
      try {
        const res = await API(`/tasks/${tid}/run`, { method: 'POST' });
        alert(`已提交 ${res.run_ids.length} 次运行`);
        location.hash = '#runs';
      } catch (err) {
        alert('提交失败: ' + err.message);
        e.target.disabled = false;
      }
    }
  };
}

// ===================== Runs (SSE 实时) =====================
function renderRuns() {
  paintRuns(state.runs);
  if (state.runsEventSource) state.runsEventSource.close();
  state.runsEventSource = new EventSource('/api/runs/stream');
  state.runsEventSource.addEventListener('runs', (e) => {
    try {
      state.runs = JSON.parse(e.data);
      paintRuns(state.runs);
    } catch {}
  });
  // 首次也拉一下
  API('/runs').then(rs => { state.runs = rs; paintRuns(rs); }).catch(() => {});
}

function paintRuns(runs) {
  const body = $('#runs-body');
  if (!body) return;
  const accMap = Object.fromEntries(state.accounts.map(a => [a.id, a.name]));
  const taskMap = Object.fromEntries(state.tasks.map(t => [t.id, t]));
  body.innerHTML = runs.map(r => {
    const task = taskMap[r.task_id];
    const tname = task ? `#${task.topic_no} ${escapeHTML(task.title)}` : `task#${r.task_id}`;
    const dur = (r.started_at && r.ended_at) ? `${(r.ended_at - r.started_at).toFixed(0)}s` :
                (r.started_at ? `${(Date.now()/1000 - r.started_at).toFixed(0)}s` : '-');
    return `
      <tr>
        <td><code>${r.id}</code></td>
        <td>${tname}</td>
        <td>${escapeHTML(accMap[r.account_id] || `acc#${r.account_id}`)}</td>
        <td><span class="pill pill-${r.status}">${r.status}</span></td>
        <td>${dur}</td>
        <td>${r.exit_code ?? '-'}</td>
        <td><button class="btn btn-sm" data-detail="${r.id}">详情</button></td>
      </tr>
    `;
  }).join('') || '<tr><td colspan="7" class="muted" style="text-align:center;padding:24px">暂无运行</td></tr>';

  body.onclick = (e) => {
    const rid = e.target.dataset.detail;
    if (rid) openRunDetail(rid);
  };
}

async function openRunDetail(rid) {
  $('#modal-content').innerHTML = '<p class="muted">加载中…</p>';
  openModal('#modal');
  try {
    const [run, files, stats] = await Promise.all([
      API(`/runs/${rid}`),
      API(`/runs/${rid}/files`).catch(() => []),
      API(`/runs/${rid}/stats`).catch(() => ({})),
    ]);
    let transcript = '';
    try {
      const r = await fetch(`/api/runs/${rid}/transcript`);
      if (r.ok) transcript = await r.text();
    } catch {}

    $('#modal-content').innerHTML = `
      <h3>Run <code>${rid}</code> <span class="pill pill-${run.status}">${run.status}</span></h3>

      <div class="detail-section">
        <h4>统计</h4>
        <div class="stats-grid">
          <div class="stat-box"><div class="stat-label">输入 token</div><div class="stat-value">${stats.tokens_in ?? '-'}</div></div>
          <div class="stat-box"><div class="stat-label">输出 token</div><div class="stat-value">${stats.tokens_out ?? '-'}</div></div>
          <div class="stat-box"><div class="stat-label">请求数</div><div class="stat-value">${stats.requests ?? '-'}</div></div>
          <div class="stat-box"><div class="stat-label">退出码</div><div class="stat-value">${run.exit_code ?? '-'}</div></div>
        </div>
      </div>

      <div class="detail-section">
        <h4>产物文件 (${files.length})</h4>
        <div class="file-tree">
          ${files.length ? files.map(f => `
            <div class="${f.type}">${escapeHTML(f.path)}${f.size != null ? `<span class="size">${formatSize(f.size)}</span>` : ''}</div>
          `).join('') : '<div class="muted">（空）</div>'}
        </div>
      </div>

      <div class="detail-section">
        <h4>Transcript</h4>
        <pre>${transcript ? escapeHTML(transcript) : '（暂无）'}</pre>
      </div>

      ${run.error ? `<div class="detail-section"><h4>错误</h4><pre>${escapeHTML(run.error)}</pre></div>` : ''}
    `;
  } catch (e) {
    $('#modal-content').innerHTML = `<p>加载失败: ${escapeHTML(e.message)}</p>`;
  }
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
    closeModal(sel);
  }
  if (e.target.classList && e.target.classList.contains('modal')) {
    const id = '#' + e.target.id;
    if (id === '#acc-modal' && typeof endAccLogin === 'function') {
      return endAccLogin({ alsoCloseModal: true });
    }
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
        closeModal('#' + m.id);
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
bindShortcuts();
