/**
 * vibecoding-100 bench WebUI
 * 纯原生 JS + Hash 路由 + Fetch + SSE
 */

const API = (path, opts = {}) =>
  fetch('/api' + path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  }).then(async (r) => {
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

  $('#add-account').onclick = () => openModal('#acc-modal');
  $('#acc-form').onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const body = {};
    for (const [k, v] of fd) if (v) body[k] = k.endsWith('_port') ? Number(v) : v;
    try {
      await API('/accounts', { method: 'POST', body: JSON.stringify(body) });
      closeModal('#acc-modal');
      e.target.reset();
      renderAccounts();
    } catch (err) { alert('创建失败: ' + err.message); }
  };
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
            <div class="${f.type}">${f.type === 'dir' ? '📁' : '📄'} ${escapeHTML(f.path)}${f.size != null ? `<span class="size">${formatSize(f.size)}</span>` : ''}</div>
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
    closeModal(sel);
  }
  if (e.target.classList && e.target.classList.contains('modal')) {
    closeModal('#' + e.target.id);
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

// 启动
navigate();
