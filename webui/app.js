/**
 * vibecoding-bench WebUI
 * 纯原生 JS + Hash 路由 + Fetch + SSE
 */

const RUNTIME_BASE = location.pathname.startsWith('/runtime') ? '/runtime' : '';
const API = (path, opts = {}) =>
  fetch(RUNTIME_BASE + '/api' + path, {
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
    ...opts,
  }).then(async (r) => {
    // 401:session 过期或未登录 → 全局弹登录框,中止当前调用
    if (r.status === 401 && !path.startsWith('/auth/')) {
      if (!RUNTIME_BASE) showAuthModal();
      const error = new Error(RUNTIME_BASE ? '统一后台会话已过期，请重新进入环境与任务页面' : 'auth required');
      error.status = 401;
      throw error;
    }
    if (!r.ok) {
      let msg = `${r.status} ${r.statusText}`;
      try { const j = await r.json(); msg = j.detail || msg; } catch {}
      const error = new Error(msg);
      error.status = r.status;
      throw error;
    }
    return r.json();
  });

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const state = {
  accounts: [],
  accountLoginMessage: '',
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
  environments: renderEnvironments,
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

/** 加载固定环境状态及空闲维护入口。@return 页面渲染完成。 */
async function renderEnvironments() {
  const rows = await API('/environments');
  const view = $('#view');
  view.innerHTML = '<h2>固定账号环境</h2><p>停止和重建会保留 HOME、身份和证据。画像校正只适用于没有运行历史的未绑定账号，保留原 HOME 和登录凭据。</p>' +
    rows.map(row => `<article class="card"><h3>${escapeHTML(row.name)}</h3><p>${escapeHTML(row.state)} · ${row.busy ? '执行中' : '无 CLI 作业'} · ${escapeHTML(row.fingerprint.hostname)} · ${escapeHTML(row.fingerprint.mem)}</p><p>环境 ${escapeHTML(row.environment_id)} · 容器代次 ${row.generation} · profile v${escapeHTML(row.fingerprint.profile_version || 1)} · ${escapeHTML(row.fingerprint.tz)} / ${escapeHTML(row.fingerprint.lang)}</p><p>${escapeHTML(row.identity_status)} · CLI ${escapeHTML((row.cli_versions || []).join(", "))}</p><p>${escapeHTML(Object.entries(row.role_status || {}).map(([role, status]) => `${({cli:"CLI",network:"网络",sender:"API"})[role] || role}: ${status}`).join(" · "))}</p>${['stop', 'rebuild', 'reconcile'].map(operation => `<button data-environment="${escapeHTML(row.environment_id)}" data-operation="${operation}" ${row.busy ? 'disabled' : ''}>${({stop:'停止',rebuild:'重建容器',reconcile:'故障对账'})[operation]}</button>`).join('')}<button data-environment="${escapeHTML(row.environment_id)}" data-operation="reprofile" ${row.can_reprofile ? '' : 'disabled'} title="${escapeHTML(row.reprofile_message || '校正保留原登录凭据')}">校正画像</button></article>`).join('');
  $$('[data-operation]', view).forEach(button => button.addEventListener('click', async () => {
    const reprofile = button.dataset.operation === 'reprofile';
    const message = reprofile
      ? '画像校正会生成新的固定环境参数，保留已有登录凭据。确认继续？'
      : '确认在账号空闲时执行此维护操作？持久数据会保留。';
    if (!confirm(message)) return;
    try {
      await API(`/environments/${button.dataset.environment}/maintenance`, { method: 'POST', body: JSON.stringify({ operation: button.dataset.operation }) });
      if (reprofile) {
        alert('画像已校正，已有登录凭据保留，可继续运行任务。');
        location.hash = '#accounts';
        return;
      }
      await renderEnvironments();
    } catch (error) {
      alert(error.message);
    }
  }));
}

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

/**
 * 展示绑定、养号调度与独立额度阈值。
 * @param {Object} account 账号与服务端养号摘要
 * @return {string} 已转义的状态 HTML
 */
function renderWarmupStatus(account) {
  const thresholds = [['5h', account.warmup_quota_5h_limit_percent], ['7d', account.warmup_quota_7d_limit_percent]]
    .filter(([, value]) => value != null)
    .map(([name, value]) => `${name} 已用 ≥ ${value}%`).join(' · ');
  const quotaStatuses = [
    ['普通任务', account.quota_policy],
    ['养号', account.warmup_quota],
  ].filter(([, quota]) => quota?.enabled).map(([label, quota]) => {
    const message = quota.message || (quota.blocked ? '等待额度更新' : '当前可启动');
    const resume = quota.resume_at
      ? `<div>恢复机会 ${escapeHTML(formatWarmupTime(quota.resume_at))}</div>`
      : '';
    return `<div class="warmup-error"><strong>${label}</strong>：${escapeHTML(message)}${resume}</div>`;
  }).join('');
  if (account.cc2api_account_id == null && !Number(account.warmup_enabled || 0)) {
    return `<span class="pill pill-queued">未绑定</span>
      ${thresholds ? `<div class="muted">普通任务阈值：${escapeHTML(thresholds)}</div>` : ''}
      ${quotaStatuses}`;
  }
  const enabled = Number(account.warmup_enabled || 0) === 1;
  const status = String(account.warmup_last_status || (enabled ? 'scheduled' : 'off'));
  const statusClass = {
    off: 'pill-queued',
    scheduled: 'pill-success',
    preparing: 'pill-running',
    queued: 'pill-queued',
    quota_wait: 'pill-quota_wait',
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
    <div><code>${account.cc2api_account_id == null ? '本地 CLI' : `cc#${escapeHTML(account.cc2api_account_id)}`}</code> <span class="pill ${statusClass}">${escapeHTML(status === 'quota_wait' ? '额度等待' : status)}</span></div>
    <div>${escapeHTML(account.warmup_interval_min_hours || 3)}-${escapeHTML(account.warmup_interval_max_hours || 5)}h</div>
    <div class="muted">next ${escapeHTML(formatWarmupTime(account.warmup_next_run_at))}</div>
    ${thresholds ? `<div class="muted">普通任务 / 养号阈值：${escapeHTML(thresholds)}</div>` : ''}
    ${quotaStatuses}
    ${error}
  `;
}

/**
 * 分别载入正式账号与登录草稿，只有正式账号进入共享任务选择状态。
 * @return {Promise<void>} 账号列表与操作入口就绪
 */
async function renderAccounts() {
  try {
    [state.accounts, state.loginDrafts] = await Promise.all([API('/accounts'), API('/accounts/login-drafts', { cache: 'no-store' })]);
  } catch (e) { return alert('加载账号失败: ' + e.message); }

  const body = $('#accounts-body');
  const loginResult = $('#account-login-result');
  loginResult.textContent = state.accountLoginMessage;
  loginResult.classList.toggle('hidden', !state.accountLoginMessage);
  body.innerHTML = state.accounts.map(a => `
    <tr>
      <td>${a.id}</td>
      <td><strong>${escapeHTML(a.name)}</strong></td>
      <td><code>${escapeHTML(a.profile_path)}</code></td>
      <td>${renderProxyEndpoint(a)}</td>
      <td>${renderAccountTimezone(a)}</td>
      <td>${renderOauthTokenStatus(a)}${renderPassiveQuota(a.passive_quota)}</td>
      <td class="warmup-status">${renderWarmupStatus(a)}</td>
      <td>${a.enabled ? '✓' : '✗'}</td>
      <td><div class="op-actions account-actions">
        <button class="btn btn-sm" data-quota="${a.id}">额度</button>
        ${a.cc2api_account_id == null ? `<button type="button" class="btn btn-sm" data-cc2-create="${a.id}">创建 cc2api 账号</button>
        <button type="button" class="btn btn-sm" data-cc2-bind="${a.id}">关联已有账号</button>` :
          (RUNTIME_BASE ? `<button type="button" class="btn btn-sm" data-cc2-process="${a.id}">更新进程指标</button>` : '')}
        <button class="btn btn-sm" data-warmup-config="${a.id}">养号 / 额度</button>
        ${Number(a.warmup_enabled || 0) === 1 ? `<button class="btn btn-sm btn-primary" data-warmup-now="${a.id}">立即运行</button>` : ''}
        ${Number(a.warmup_enabled || 0) !== 1 && (a.cc2api_account_id != null || a.warmup_last_status === 'paused') ? `<button class="btn btn-sm" data-warmup-resume="${a.id}">恢复</button>` : ''}
        ${a.cc2api_account_id == null || RUNTIME_BASE ? `<button class="btn btn-sm" data-relogin="${a.id}">重新授权</button>` : ''}
        ${a.cc2api_account_id != null ? `<button class="btn btn-sm btn-danger" data-cc2-unbind="${a.id}">解绑</button>` : ''}
        <button class="btn btn-sm btn-danger" data-del="${a.id}">删除</button>
      </div></td>
    </tr>
  `).join('') + (state.loginDrafts || []).map(draft => {
    const phase = { preparing: '准备登录', authorizing: '登录中 · 未提交', ready_to_submit: '认证通过 · 待提交', ended: '终端已结束',
      interrupted: '登录已中断', cancelled: '已取消 · 环境保留', submitting: '保存未完成 · 请继续提交', reconcile: '需检查 / 对账', deleting: '清理未完成 · 可重试' }[draft.state] || '未完成登录';
    const id = escapeHTML(draft.environment_id);
    return `<tr class="account-draft-row">
      <td><span class="muted">草稿</span></td><td><strong>${escapeHTML(draft.name)}</strong></td>
      <td><strong>${escapeHTML(phase)}</strong><div class="muted">${escapeHTML(draft.message || (draft.credentials_present && !draft.credentials_ready ? '保留授权产物；继续后检查认证状态' : '尚未保存账号'))}</div></td>
      <td>${escapeHTML(draft.proxy_known ? (draft.proxy_summary || '未配置代理') : '配置待检查')}</td><td>—</td><td>未提交</td>
      <td>不参与任务与养号</td><td>—</td><td><div class="op-actions account-actions">
        <button type="button" class="btn btn-sm" data-draft-resume="${id}" ${draft.can_resume ? '' : 'disabled'}>继续登录</button>
        <button type="button" class="btn btn-sm" data-draft-restart="${id}" ${draft.can_restart ? '' : 'disabled'}>重新登录</button>
        ${draft.session_id ? `<button type="button" class="btn btn-sm" data-draft-cancel="${id}" ${draft.can_restart ? '' : 'disabled'}>取消登录</button>` : ''}
        <button type="button" class="btn btn-sm btn-danger" data-draft-delete="${id}" ${draft.can_delete ? '' : 'disabled'}>删除草稿</button>
        ${draft.can_reconcile ? `<button type="button" class="btn btn-sm" data-draft-reconcile="${id}">恢复检查</button>` : ''}
        ${draft.state === 'reconcile' ? '<a class="btn btn-sm" href="#environments">查看环境</a>' : ''}
      </div></td></tr>`;
  }).join('') || '<tr><td colspan="9" class="muted empty-cell">暂无账号</td></tr>';

  body.onclick = async (e) => {
    const draftId = e.target.dataset.draftResume || e.target.dataset.draftRestart || e.target.dataset.draftCancel || e.target.dataset.draftDelete || e.target.dataset.draftReconcile;
    if (draftId) {
      const draft = state.loginDrafts.find(item => item.environment_id === draftId);
      if (!draft) return;
      if (e.target.dataset.draftDelete && !confirm(`删除未提交草稿「${draft.name}」？将取消登录，并删除专属容器、HOME、缓存及未提交授权产物。`)) return;
      e.target.disabled = true;
      try {
        if (e.target.dataset.draftDelete) {
          await API(`/accounts/login-drafts/${draftId}?generation=${encodeURIComponent(draft.generation)}`, { method: 'DELETE' });
        } else if (e.target.dataset.draftReconcile) {
          await API(`/accounts/login-drafts/${draftId}/reconcile`, { method: 'POST', body: JSON.stringify({ generation: draft.generation }) });
        } else if (e.target.dataset.draftCancel) {
          await API(`/accounts/login/${draft.session_id}`, { method: 'DELETE' });
        } else {
          await openLoginDraft(draft, e.target.dataset.draftRestart ? 'restart' : 'resume');
        }
      } catch (error) { alert('草稿操作未完成：' + error.message); }
      finally { await renderAccounts(); }
      return;
    }
    const id = e.target.dataset.del;
    const quotaId = e.target.dataset.quota;
    const reloginId = e.target.dataset.relogin;
    const createId = e.target.dataset.cc2Create;
    const bindId = e.target.dataset.cc2Bind;
    const processId = e.target.dataset.cc2Process;
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
    if (bindId) {
      const account = state.accounts.find(a => String(a.id) === String(bindId));
      if (!account) return;
      e.target.disabled = true;
      try { await openCc2apiBindingModal(account); }
      catch (error) { alert('加载可关联账号失败：' + error.message); }
      finally { e.target.disabled = false; }
      return;
    }
    if (createId || processId) {
      e.target.disabled = true;
      try {
        const result = await API(`/accounts/${createId || processId}/cc2api/${createId ? 'create' : 'process'}`, { method: 'POST' });
        state.accountLoginMessage = createId
          ? `已创建 cc2api 账号 #${result.cc2api_account.id} 并完成关联`
          : `已更新 cc2api 账号 #${result.cc2api_account_id} 的进程指标${result.canonical_process.observation?.sample_count ? '' : '；CLI RSS 尚未采集'}`;
        await renderAccounts();
      } catch (err) {
        alert((createId ? '创建 cc2api 账号失败：' : '更新进程指标失败：') + err.message);
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
  $('#acc-login-reconnect').onclick = () => state.accLogin?.connection?.reconnect();
  $('#acc-login-restart').onclick = restartAccLogin;
  $('#acc-login-copy').onclick = copyAccLoginURL;
  $('#acc-login-open').onclick = () => {
    if (state.accLogin?.authorizationURL) window.open(state.accLogin.authorizationURL, '_blank', 'noopener,noreferrer');
  };
  $('#acc-modal-close').onclick = () => endAccLogin({ alsoCloseModal: true });
  $('#warmup-form').onsubmit = saveWarmupConfig;
  $('#cc2api-binding-form').onsubmit = saveCc2apiBinding;
}

/**
 * 独立选择已有 cc2api 账号，关联动作不修改养号设置。
 * @param {Object} account 当前未关联的本地账号
 * @return {Promise<void>} 候选账号加载后显示窗口
 */
async function openCc2apiBindingModal(account) {
  state.cc2apiAccounts = await API('/cc2api/accounts');
  const form = $('#cc2api-binding-form');
  form.account_id.value = account.id;
  const available = state.cc2apiAccounts.filter(item => !state.accounts.some(a =>
    a.cc2api_account_id != null && Number(a.cc2api_account_id) === Number(item.id)));
  form.cc2api_account_id.innerHTML = '<option value="">请选择已有账号</option>' + available.map(item =>
    `<option value="${escapeHTML(item.id)}">#${escapeHTML(item.id)} ${escapeHTML(item.name || 'OAuth')} · ${escapeHTML(item.email_masked || '-')}</option>`).join('');
  form.querySelector('button[type="submit"]').disabled = available.length === 0;
  $('#cc2api-binding-hint').textContent = available.length
    ? '关联会核对登录身份和设备，保留目标账号配置；不会创建账号或修改养号设置。'
    : '当前没有可关联的账号。可先在账号页创建 cc2api 账号。';
  $('#cc2api-binding-title').textContent = `#${account.id} ${account.name}`;
  openModal('#cc2api-binding-modal');
}

/**
 * 提交用户显式选择的关联目标，完成后保留明确结果。
 * @param {SubmitEvent} event 关联表单提交事件
 * @return {Promise<void>} 关联结束并刷新账号列表
 */
async function saveCc2apiBinding(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  button.disabled = true;
  try {
    const result = await API(`/accounts/${Number(form.account_id.value)}/cc2api/bind`, {
      method: 'POST', body: JSON.stringify({ cc2api_account_id: Number(form.cc2api_account_id.value) }),
    });
    state.accountLoginMessage = `已关联现有 cc2api 账号 #${result.cc2api_account.id}，保留该账号原配置`;
    closeModal('#cc2api-binding-modal');
    await renderAccounts();
  } catch (error) { alert('关联已有账号失败：' + error.message); }
  finally { button.disabled = false; }
}

/**
 * 载入账号养号配置及普通任务、养号共用的两个独立阈值。
 * @param {Object} account 当前账号
 * @return {Promise<void>} 表单就绪后完成
 */
async function openWarmupModal(account) {
  const form = $('#warmup-form');
  form.account_id.value = account.id;
  form.interval_min_hours.value = account.warmup_interval_min_hours || 3;
  form.interval_max_hours.value = account.warmup_interval_max_hours || 5;
  form.enabled.checked = Number(account.warmup_enabled || 0) === 1;
  for (const window of ['5h', '7d']) {
    const input = form.elements[`warmup_quota_${window}_limit_percent`];
    const enabled = form.elements[`quota_${window}_enabled`];
    const value = account[`warmup_quota_${window}_limit_percent`];
    enabled.checked = value != null;
    input.value = value ?? '';
    enabled.onchange = () => updateWarmupQuotaInputs(form);
    input.oninput = () => updateWarmupQuotaInputs(form);
  }
  updateWarmupQuotaInputs(form);
  updateWarmupBindingState(form);
  $('#warmup-modal-title').textContent = `#${account.id} ${account.name}`;
  openModal('#warmup-modal');
}

/**
 * 本地 OAuth 账号可独立养号，已有绑定时使用 cc2api 凭据。
 * @param {HTMLFormElement} form 养号与额度配置表单
 * @return {void} 不返回值
 */
function updateWarmupBindingState(form) {
  const account = state.accounts.find(item => String(item.id) === String(form.account_id.value));
  const bound = account?.cc2api_account_id != null;
  form.enabled.disabled = false;
  $('#warmup-binding-hint').textContent = bound
    ? `定时养号使用已关联的 cc2api 账号 #${account.cc2api_account_id}；此处只修改养号与额度设置。`
    : '使用此账号已有的 CLI OAuth 凭据，可独立启用定时养号与额度阈值。';
}

/**
 * 更新账号级阈值表单的可编辑状态及已用/剩余说明。
 * @param {HTMLFormElement} form 养号配置表单
 * @return {void} 不返回值
 */
function updateWarmupQuotaInputs(form) {
  for (const window of ['5h', '7d']) {
    const input = form.elements[`warmup_quota_${window}_limit_percent`];
    const enabled = form.elements[`quota_${window}_enabled`].checked;
    input.disabled = !enabled;
    input.required = enabled;
    const value = Number(input.value);
    $(`#warmup-quota-${window}-hint`).textContent = !enabled ? '已关闭，沿用额度用满保护'
      : input.value && Number.isInteger(value) && value >= 1 && value <= 100
        ? `观测已用达到 ${value}%（剩余 ${100 - value}%）时强制结束当前普通任务与养号轮次，后续执行等待`
        : '请输入 1～100 的已用百分比整数';
  }
}

/**
 * 原子保存养号间隔及阈值，关闭额度限制时显式提交 null。
 * @param {SubmitEvent} e 配置提交事件
 * @return {Promise<void>} 保存并刷新账号状态后完成
 */
async function saveWarmupConfig(e) {
  e.preventDefault();
  const form = e.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  const accountId = Number(form.account_id.value);
  const payload = {
    enabled: form.enabled.checked,
    interval_min_hours: Number(form.interval_min_hours.value),
    interval_max_hours: Number(form.interval_max_hours.value),
    warmup_quota_5h_limit_percent: form.quota_5h_enabled.checked ? Number(form.warmup_quota_5h_limit_percent.value) : null,
    warmup_quota_7d_limit_percent: form.quota_7d_enabled.checked ? Number(form.warmup_quota_7d_limit_percent.value) : null,
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
    alert('保存养号与额度配置失败: ' + err.message);
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

/**
 * 显示已观察到的额度；渲染过程不触发主动查询。
 * @param {Object} quota 被动额度摘要
 * @return {string} 已转义的 HTML
 */
function renderPassiveQuota(quota) {
  if (quota?.account_error) return `<div class="passive-quota">${escapeHTML(quota.message)}</div>`;
  if (!quota?.known) return '<div class="passive-quota muted">被动额度：未知</div>';
  const source = quota.source === 'manual' ? '额度记录（手动更新）'
    : quota.source === 'automatic' ? '额度记录（历史查询）' : '被动额度';
  const windows = ['five_hour', 'seven_day'].map(key => {
    const window = quota.windows?.[key];
    const name = key === 'five_hour' ? '5h' : '7d';
    if (!window) return `${name} 未知`;
    const expired = window.reset_at && window.reset_at <= Date.now() / 1000;
    const used = Number(window.utilization);
    const amount = window.utilization == null || !Number.isFinite(used) ? '用量未知'
      : `已用 ${used.toFixed(1)}% / 剩余 ${Math.max(0, 100 - used).toFixed(1)}%`;
    return `${name} ${expired ? '上次' : ''}${amount}${expired ? '（窗口已到期）' : ''}`;
  }).join(' · ');
  const reason = quota.message ? `<div>${escapeHTML(quota.message)}</div>` : '';
  const resume = quota.exhausted?.length ? `<div>${quota.resume_at ? `恢复机会 ${escapeHTML(formatWarmupTime(quota.resume_at))}` : '暂无可信恢复时间'}</div>` : '';
  return `<div class="passive-quota muted">${source}：${escapeHTML(windows)}<div>观察于 ${escapeHTML(formatWarmupTime(quota.observed_at))}</div>${reason}${resume}</div>`;
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
  const bound = Boolean(account?.cc2api_account_id != null);
  for (const name of ['upstream_proxy_scheme', 'upstream_socks5_host', 'upstream_socks5_port', 'upstream_socks5_user', 'upstream_socks5_pass', 'timezone']) {
    form.elements[name].disabled = bound;
  }
  $('#acc-proxy-url').disabled = bound;
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

/**
 * 以用户配置开始登录，启动中关闭必须等待服务端返回后收口。
 * @param {Object} body 登录配置
 * @return {Promise<void>} 终端就绪或失败处理结束
 */
async function startAccLogin(body) {
  const loginState = state.accLogin || {};
  state.accLogin = loginState;
  loginState.starting = true;
  const startButton = $('#acc-form button[type="submit"]');
  startButton.disabled = true;
  let resp;
  try {
    resp = await API('/accounts/login/start', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  } catch (e) {
    loginState.starting = false;
    startButton.disabled = false;
    if (state.accLogin === loginState && loginState.closeRequested) {
      await endAccLogin({ alsoCloseModal: true, skipServerCancel: true });
      return;
    }
    return alert('启动登录会话失败: ' + e.message);
  }
  loginState.starting = false;
  startButton.disabled = false;
  if (state.accLogin !== loginState) {
    // 启动 HTTP 期间关窗后，仍等返回 SID 才取消，避免遗留看不见的登录会话。
    API(`/accounts/login/${resp.session_id}`, { method: 'DELETE' }).catch(() => {});
    return;
  }
  await showAccLoginSession(resp, body, loginState);
  await renderAccounts();
}

/**
 * 打开账号列表中的原草稿，继续与重登使用同一终端生命周期。
 * @param {Object} draft 页面草稿及代次
 * @param {string} action resume 或 restart
 * @return {Promise<void>} 会话窗口就绪后完成
 */
async function openLoginDraft(draft, action) {
  openAccLoginModal();
  const login = state.accLogin;
  login.starting = true;
  try {
    const resp = await API(`/accounts/login-drafts/${draft.environment_id}/${action}`, {
      method: 'POST', body: JSON.stringify({ generation: draft.generation }),
    });
    login.starting = false;
    await showAccLoginSession(resp, { name: draft.name }, login);
  } catch (error) {
    login.starting = false;
    await endAccLogin({ alsoCloseModal: true, skipServerCancel: true });
    throw error;
  }
}

/**
 * 展示新建或恢复的登录，统一收口启动期间的关闭请求。
 * @param {Object} resp 服务端会话信息
 * @param {Object} body 原提交配置
 * @param {Object} loginState 本窗口的状态对象
 * @return {Promise<void>} 完成终端初始化或确认取消
 */
async function showAccLoginSession(resp, body, loginState) {
  if (state.accLogin !== loginState) return;
  // 保存 proxy/name 给 commit 用
  state.accLogin.body = body;
  state.accLogin.mode = loginState.mode || 'new';
  state.accLogin.accountId = loginState.accountId || null;
  state.accLogin.sid = resp.session_id;
  state.accLogin.name = resp.name;
  state.accLogin.reconnectable = Boolean(resp.reconnectable);
  state.accLogin.environmentId = resp.environment_id || null;
  state.accLogin.draftGeneration = resp.draft_generation || null;
  state.accLogin.authorizationURL = null;
  loginState.codeMode = Boolean(RUNTIME_BASE || resp.environment_id || resp.reconnectable);
  loginState.loginPhase = resp.reconnectable ? 'authorizing' : 'unknown';
  loginState.codeStatus = 'idle';
  loginState.codeSending = false;
  $('#acc-code-form').classList.toggle('hidden', !loginState.codeMode);
  $('#acc-auth-code').value = '';
  $('#acc-auth-code').type = 'password';
  $('#acc-code-toggle').textContent = '显示授权码';
  $('#acc-code-toggle').setAttribute('aria-pressed', 'false');
  $('#acc-code-status').textContent = '尚未发送';
  $('#acc-login-input-hint').textContent = loginState.codeMode
    ? '打开授权链接完成登录。授权码优先填入下方输入框并发送；CLI 出现其它确认或选择时，点击黑色终端直接操作。请勿在两处重复发送同一授权码。认证检查通过后点击“提交保存”。'
    : '打开授权链接完成登录，将完整授权码粘回终端后按 Enter，再点击“提交保存”。';
  $('#acc-auth-code').oninput = updateAccCodeControls;
  $('#acc-code-form').onsubmit = event => { event.preventDefault(); sendAccLoginCode(); };
  $('#acc-code-toggle').onclick = () => {
    const input = $('#acc-auth-code');
    input.type = input.type === 'password' ? 'text' : 'password';
    $('#acc-code-toggle').textContent = input.type === 'password' ? '显示授权码' : '隐藏授权码';
    $('#acc-code-toggle').setAttribute('aria-pressed', String(input.type === 'text'));
  };
  $('#acc-code-query').onclick = queryAccCodeReceipt;
  updateAccCodeControls();
  $('#acc-auth-url').value = '';
  $('#acc-login-copy').disabled = true;
  $('#acc-login-open').disabled = true;
  $('#acc-login-reconnect').disabled = true;
  $('#acc-login-restart').classList.add('hidden');
  $('#acc-login-link-status').textContent = '等待 CLI 输出授权链接';

  $('#acc-login-sid').textContent = resp.session_id;
  $('#acc-login-sidecar').textContent = resp.has_sidecar ? 'yes' : 'no (direct)';
  $('#acc-login-name').textContent = resp.name;
  $('#acc-modal-stage').textContent = 'step 2 · terminal';

  showAccStep('terminal');
  if (loginState.closeRequested) {
    // 启动期间请求关闭时保留窗口，取得 SID 后等待取消确认；失败仍可重试取消。
    await endAccLogin({ alsoCloseModal: true });
    return;
  }
  try { await attachAccLoginTerminal(resp.ws_path); }
  catch (error) {
    if (state.accLogin === loginState) $('#acc-login-connection-status').textContent = '终端初始化失败：' + error.message + '；可取消后重新登录';
  }
}

/**
 * 已结束的登录明确重启授权，不尝试重连死亡的终端。
 * @return {Promise<void>} 原环境新会话打开后完成
 */
async function restartAccLogin() {
  const login = state.accLogin;
  if (!login || login.closing || login.committing || login.starting || login.codeSending) return;
  const draft = { environment_id: login.environmentId, generation: login.draftGeneration, name: login.name };
  const account = state.accounts.find(item => item.id === login.accountId);
  await endAccLogin({ alsoCloseModal: true });
  if (state.accLogin) return;
  try {
    if (draft.environment_id) await openLoginDraft(draft, 'restart');
    else openAccLoginModal(account || null);
  } catch (error) { alert('重新登录失败：' + error.message); }
  await renderAccounts();
}

async function attachAccLoginTerminal(wsPath) {
  const login = state.accLogin;
  let termState;
  try { termState = await attachTerminal('#acc-login-xterm', wsPath, 'running', {
    autoReconnect: login.reconnectable,
    startStopped: !login.reconnectable && Boolean(login.environmentId || RUNTIME_BASE),
    isActive: () => state.accLogin === login && !login.closing,
    onSocket: socket => { if (state.accLogin === login) login.ws = socket; },
    onState: message => {
      if (state.accLogin !== login) return;
      $('#acc-login-connection-status').textContent = message === '终端已连接' && login.codeMode
        ? '终端已连接，可点击黑框进行 CLI 交互；授权码建议使用上方输入框'
        : message;
    },
  }); } catch (error) {
    if (!login.codeMode) throw error;
    // 授权码走独立 HTTP；输出组件失败不能阻断认证状态轮询和提交反馈。
    termState = { stop: message => { if (state.accLogin === login) $('#acc-login-connection-status').textContent = message; }, dispose() {} };
    $('#acc-login-connection-status').textContent = '输出终端未连接；授权码仍可通过输入框发送';
  }
  if (state.accLogin !== login) { termState.dispose(); return; }

  login.term = termState.term;
  login.fit = termState.fit;
  login.ws = termState.ws;
  login.connection = termState;
  login.onResize = termState.onResize;
  $('#acc-login-reconnect').disabled = !login.reconnectable || typeof termState.reconnect !== 'function';
  if (login.reconnectable || login.environmentId || RUNTIME_BASE) {
    /** 只在当前登录窗内串行查状态，不依赖 WS 首次输出来找链接。 */
    const poll = async () => {
      if (state.accLogin !== login) return;
      if (login.closing) { login.pollTimer = setTimeout(poll, 2000); return; }
      try {
        const status = await API(`/accounts/login/${login.sid}/status`, { cache: 'no-store' });
        if (state.accLogin !== login || login.closing) return;
        login.authorizationURL = status.authorization_url || null;
        login.loginPhase = status.phase;
        updateAccCodeControls();
        $('#acc-auth-url').value = login.authorizationURL || '';
        $('#acc-login-copy').disabled = !login.authorizationURL;
        $('#acc-login-open').disabled = !login.authorizationURL;
        $('#acc-login-link-status').textContent = status.credentials_ready ? 'CLI 认证检查通过，可以提交保存' : (login.authorizationURL ? '授权链接已就绪，请在下方输入完整授权码并发送' : (status.reconnectable ? '等待 CLI 输出授权链接' : status.message || '登录已结束'));
        $('#acc-login-restart').classList.toggle('hidden', !status.restartable);
        if (!status.reconnectable) {
          login.pollStopped = true;
          termState.stop(status.message || (status.phase === 'committed' ? '登录已完成' : '凭据同步待确认，可重试提交或在环境页对账'));
          $('#acc-login-reconnect').disabled = true;
          return;
        }
      } catch (error) {
        if (state.accLogin !== login || login.closing) return;
        if ([401, 403, 404, 409, 410].includes(error.status)) {
          login.pollStopped = true;
          login.loginPhase = 'ended';
          updateAccCodeControls();
          termState.stop(error.message);
          $('#acc-login-reconnect').disabled = true;
          $('#acc-login-restart').classList.toggle('hidden', ![404, 409, 410].includes(error.status));
          login.authorizationURL = null;
          $('#acc-auth-url').value = '';
          $('#acc-login-copy').disabled = true;
          $('#acc-login-open').disabled = true;
          return;
        }
        $('#acc-login-link-status').textContent = '暂时无法读取登录状态，稍后重试';
      } finally {
        // 取消请求失败后仍要继续读状态，不能因请求中的临时 closing 丢掉轮询。
        if (state.accLogin === login && !login.pollStopped) login.pollTimer = setTimeout(poll, 2000);
      }
    };
    poll();
  }
}

/**
 * 复制完整授权链接，兼容 HTTP 页面的剪贴板限制。
 * @return {Promise<void>} 显示实际复制结果或选中文本供手动复制。
 */
async function copyAccLoginURL() {
  const login = state.accLogin;
  if (!login?.authorizationURL) return;
  let copied = false;
  if (window.isSecureContext && navigator.clipboard?.writeText) {
    try { await navigator.clipboard.writeText(login.authorizationURL); copied = true; } catch {}
  }
  if (state.accLogin !== login) return;
  if (!copied) {
    const input = $('#acc-auth-url');
    input.focus();
    input.select();
    try { copied = document.execCommand('copy'); } catch {}
  }
  $('#acc-login-link-status').textContent = copied ? '授权链接已复制' : '链接已选中，请按 Ctrl+C 或长按复制';
}

/** 刷新当前授权码长度和操作许可。@return {void} 页面状态同步完成。 */
function updateAccCodeControls() {
  const login = state.accLogin;
  const input = $('#acc-auth-code');
  const blocked = !login?.codeMode || login.loginPhase !== 'authorizing' || login.closing || login.committing || login.codeSending;
  input.disabled = blocked || ['sending', 'uncertain'].includes(login?.codeStatus);
  $('#acc-code-length').textContent = `已输入 ${input.value.length} 个字符`;
  $('#acc-code-send').disabled = input.disabled || !input.value.trim();
  $('#acc-code-toggle').disabled = blocked;
  $('#acc-code-query').classList.toggle('hidden', !login?.codeRequestId || !['sending', 'uncertain'].includes(login.codeStatus));
  $('#acc-code-query').disabled = Boolean(login?.codeSending);
}

/**
 * 提交一次授权码；未知结果只查回执，不保留离线重发队列。
 * @return {Promise<void>} 投递状态已反馈，认证结果仍由状态轮询确认。
 */
async function sendAccLoginCode() {
  const login = state.accLogin;
  if (!login?.codeMode || $('#acc-code-send').disabled) return;
  const code = $('#acc-auth-code').value;
  if (code.trim().length > 8192 || /[\x00-\x1f\x7f]/.test(code)) {
    $('#acc-code-status').textContent = '授权码包含控制字符或过长，请复制完整的单行授权码';
    return;
  }
  const requestId = Array.from(crypto.getRandomValues(new Uint8Array(16)), byte => byte.toString(16).padStart(2, '0')).join('');
  login.codeRequestId = requestId;
  login.codeStatus = 'sending';
  login.codeSending = true;
  $('#acc-auth-code').value = '';
  $('#acc-code-status').textContent = '正在发送授权码…';
  updateAccCodeControls();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15000);
  try {
    const receipt = await API(`/accounts/login/${login.sid}/code`, {
      method: 'POST', body: JSON.stringify({ request_id: requestId, code }), signal: controller.signal,
    });
    if (state.accLogin !== login || login.codeRequestId !== requestId) return;
    login.codeStatus = receipt.status;
    $('#acc-code-status').textContent = receipt.message;
  } catch (error) {
    if (state.accLogin !== login || login.codeRequestId !== requestId) return;
    login.codeStatus = [401, 403, 409, 413, 422].includes(error.status) ? 'rejected' : 'uncertain';
    $('#acc-code-status').textContent = login.codeStatus === 'rejected' ? error.message : '发送结果未知，请查询本次结果并查看 CLI；不会自动重发';
  } finally {
    clearTimeout(timer);
    if (state.accLogin === login) { login.codeSending = false; updateAccCodeControls(); }
  }
}

/** 查询当前投递回执，绝不重发授权码。@return {Promise<void>} 本次结果已展示。 */
async function queryAccCodeReceipt() {
  const login = state.accLogin;
  if (!login?.codeRequestId || login.codeSending || login.closing) return;
  login.codeSending = true;
  updateAccCodeControls();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15000);
  try {
    const receipt = await API(`/accounts/login/${login.sid}/code/${login.codeRequestId}`, { cache: 'no-store', signal: controller.signal });
    if (state.accLogin !== login) return;
    login.codeStatus = receipt.status;
    $('#acc-code-status').textContent = receipt.message;
  } catch {
    if (state.accLogin !== login) return;
    login.codeStatus = 'uncertain';
    $('#acc-code-status').textContent = '回执暂时不可查，发送结果未知，请查看 CLI 或取消后重新登录';
  } finally {
    clearTimeout(timer);
    if (state.accLogin === login) { login.codeSending = false; updateAccCodeControls(); }
  }
}

/**
 * 挂载终端；登录可重连原 tmux，续聊保持原行为。
 * @param {string} hostSelector 终端宿主。
 * @param {string} wsPath 原会话路径，不保存旧票据。
 * @param {string} initialStatus 初始输入状态。
 * @param {object} options 登录连接选项和状态回调。
 * @return {Promise<object>} 当前连接与幂等收口句柄。
 */
async function attachTerminal(hostSelector, wsPath, initialStatus = 'running', options = {}) {
  const vendorDeadline = Date.now() + 10000;
  while (typeof Terminal === 'undefined' || typeof FitAddon === 'undefined') {
    if (options.isActive && !options.isActive()) throw new Error('登录窗口已关闭');
    if (Date.now() >= vendorDeadline) throw new Error('终端组件加载超时');
    await new Promise(resolve => setTimeout(resolve, 50));
  }
  if (options.isActive && !options.isActive()) throw new Error('登录窗口已关闭');

  const host = $(hostSelector);
  host.innerHTML = '';

  const term = new Terminal({
    fontFamily: '"JetBrains Mono", ui-monospace, Menlo, monospace',
    fontSize: 13,
    cursorBlink: true,
    disableStdin: Boolean(options.readOnly),
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
  let ws = null;
  let inputAllowed = false;
  let disposed = false;
  let stopped = false;
  let generation = 0;
  let retries = 0;
  let retryTimer = null;
  let heartbeatTimer = null;
  const active = () => !disposed && (!options.isActive || options.isActive());
  const notify = message => { if (active()) options.onState?.(message); };
  const stop = message => {
    stopped = true;
    inputAllowed = false;
    clearTimeout(retryTimer);
    clearInterval(heartbeatTimer);
    notify(message);
    if (ws?.readyState <= WebSocket.OPEN) ws.close();
  };
  const schedule = () => {
    if (!active() || stopped) return;
    if (!options.autoReconnect || retries >= 8) {
      notify('连接已断开，请手动重新连接');
      return;
    }
    const delay = Math.min(1000 * 2 ** retries, 8000);
    retries += 1;
    notify(`连接已断开，${delay / 1000} 秒后重连（${retries}/8）`);
    retryTimer = setTimeout(connect, delay);
  };
  /** 每次重连都重新取短票据，不重复启动 CLI 或重放离线输入。 */
  const connect = async () => {
    if (!active() || stopped) return;
    const current = ++generation;
    inputAllowed = false;
    notify('正在连接登录终端…');
    let path = wsPath.split('?')[0];
    try {
      if (RUNTIME_BASE) {
        const result = await API('/terminal-ticket', { method: 'POST', body: JSON.stringify({ path }) });
        path += '?ticket=' + encodeURIComponent(result.ticket);
      }
      if (!active() || stopped || current !== generation) return;
      const socket = new WebSocket(`${proto}//${location.host}${RUNTIME_BASE}${path}`);
      ws = socket;
      options.onSocket?.(socket);
      socket.binaryType = 'arraybuffer';
      let lastMessage = Date.now();
      let openedAt = 0;
      socket.onopen = () => {
        if (!active() || stopped || current !== generation) { socket.close(); return; }
        openedAt = Date.now();
        lastMessage = openedAt;
        inputAllowed = hostSelector !== '#continue-xterm' && initialStatus === 'running';
        socket.send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }));
        notify('终端已连接');
        if (!options.readOnly) term.focus();
        if (options.autoReconnect) {
          clearInterval(heartbeatTimer);
          heartbeatTimer = setInterval(() => {
            if (!active() || current !== generation) return;
            if (Date.now() - openedAt >= 30000) retries = 0;
            if (Date.now() - lastMessage > 30000) { socket.close(); return; }
            if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: 'ping' }));
          }, 10000);
        }
      };
      socket.onmessage = e => {
        if (!active() || current !== generation) return;
        lastMessage = Date.now();
        if (e.data instanceof ArrayBuffer) {
          term.write(new Uint8Array(e.data));
        } else if (typeof e.data === 'string') {
          try {
            const msg = JSON.parse(e.data);
            if (msg.type === 'error') term.write(`\r\n\x1b[31m${msg.msg}\x1b[0m\r\n`);
            if (msg.type === 'quota_state') {
              inputAllowed = msg.status === 'running';
              const status = $('#continue-quota-status');
              if (status) status.textContent = inputAllowed ? '可继续输入' : `${msg.message || '额度等待'}${msg.resume_at ? `；恢复机会 ${formatWarmupTime(msg.resume_at)}` : '；暂无可信恢复时间'}`;
            }
          } catch { term.write(e.data); }
        }
      };
      socket.onclose = event => {
        if (current !== generation || disposed || stopped) return;
        inputAllowed = false;
        clearInterval(heartbeatTimer);
        if (openedAt && Date.now() - openedAt >= 30000) retries = 0;
        if ([4004, 4401, 4404].includes(event.code)) { stop('登录会话已结束或鉴权失效，请重新授权'); return; }
        term.write('\r\n\x1b[90m[连接已断开]\x1b[0m\r\n');
        schedule();
      };
      socket.onerror = () => { if (current === generation && !stopped) notify('终端连接异常，等待重新连接'); };
    } catch (error) {
      if (!active() || current !== generation) return;
      if ([401, 403, 404, 410].includes(error.status)) stop(error.message);
      else schedule();
    }
  };
  const input = term.onData(data => {
    if (options.readOnly) return;
    if (active() && inputAllowed && ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'input', data }));
    // 终态原因已经确定；离线输入不能覆盖它或承诺恢复一个死亡的终端。
    else if (active() && !stopped) notify('终端未连接，输入未发送；连接恢复后请重新输入');
  });

  // xterm 只接管内部屏幕；点击黑框内边距后也要将焦点交还终端，不能停在页面上。
  const focusTerminal = event => {
    if (event.button === 0 && active() && !stopped) term.focus();
  };
  host.addEventListener('click', focusTerminal);

  const onResize = () => {
    try { fit.fit(); } catch {}
    if (active() && ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }));
    }
  };
  window.addEventListener('resize', onResize);
  if (options.startStopped) stopped = true;
  else await connect();
  return { term, fit, get ws() { return ws; }, onResize, stop,
    reconnect: () => {
      if (!active() || stopped) return;
      retries = 0;
      clearTimeout(retryTimer);
      clearInterval(heartbeatTimer);
      generation += 1;
      if (ws?.readyState <= WebSocket.OPEN) ws.close();
      connect();
    },
    dispose: () => {
      if (disposed) return;
      disposed = true;
      generation += 1;
      clearTimeout(retryTimer);
      clearInterval(heartbeatTimer);
      if (ws?.readyState <= WebSocket.OPEN) ws.close();
      input.dispose();
      host.removeEventListener('click', focusTerminal);
      window.removeEventListener('resize', onResize);
      term.dispose();
    },
  };
}

/**
 * 提交登录并展示本地保存或关联账号凭据同步的实际结果。
 * @return {Promise<void>} 提交、窗口收口及结果展示完成
 */
async function commitAccLogin() {
  const al = state.accLogin;
  if (!al || !al.sid || al.closing || al.committing || al.codeSending) return;
  al.committing = true;
  updateAccCodeControls();
  const btn = $('#acc-login-commit');
  btn.disabled = true;
  try {
    const r = await API(`/accounts/login/${al.sid}/commit`, {
      method: 'POST',
      body: JSON.stringify(al.body || { name: al.name }),
    });
    if (state.accLogin !== al) return;
    const action = r.credentials_synced ? '已重授权并同步关联账号' : (r.credentials_synced === false
      ? `${al.mode === 'relogin' ? '已重新授权' : '账号已保存'}，仅保存到本地，尚未关联 cc2api`
      : (al.mode === 'relogin' ? '已重新授权' : '账号已保存'));
    if (al.term) al.term.write(`\r\n\x1b[32m[完成] ${action} (#${r.id})\x1b[0m\r\n`);
    // commit 成功后服务端已清容器；前端关 WS + 弹窗 + 刷列表
    al.committing = false;
    await endAccLogin({ alsoCloseModal: true, skipServerCancel: true });
    state.accountLoginMessage = `最近一次登录保存：${al.name}：${action}`;
    await renderAccounts();
  } catch (e) {
    if (state.accLogin === al) {
      btn.disabled = false;
      alert('提交失败: ' + e.message + '\n\n如果还没登录成功，请先在终端完成 OAuth。');
    }
  } finally {
    al.committing = false;
    if (state.accLogin === al) updateAccCodeControls();
  }
}

async function endAccLogin({ alsoCloseModal = false, skipServerCancel = false } = {}) {
  const al = state.accLogin || {};
  if (al.closing) return;
  if (al.starting) {
    al.closeRequested = true;
    $('#acc-modal-stage').textContent = '正在等待会话启动，随后取消';
    return;
  }
  if (al.committing || al.codeSending) { $('#acc-login-connection-status').textContent = '正在确认发送或提交结果，请稍候再关闭'; return; }
  al.closing = true;
  $('#acc-auth-code').value = '';
  updateAccCodeControls();
  // 先等待服务端确认取消；结果未知时保留弹窗，不能静默丢掉暂存凭据。
  if (al.sid && !skipServerCancel) {
    try { await API(`/accounts/login/${al.sid}`, { method: 'DELETE' }); }
    catch (error) {
      al.closing = false;
      updateAccCodeControls();
      $('#acc-login-connection-status').textContent = '取消未完成：' + error.message;
      return;
    }
  }
  clearTimeout(al.pollTimer);
  $('#acc-auth-code').value = '';
  $('#acc-auth-code').oninput = null;
  $('#acc-code-form').onsubmit = null;
  $('#acc-code-toggle').onclick = null;
  $('#acc-code-query').onclick = null;
  if (al.connection) al.connection.dispose();
  // 1. 关闭 WS
  if (al.ws && al.ws.readyState <= 1) {
    try { al.ws.close(); } catch {}
  }
  // 2. 释放 xterm
  if (al.term && !al.connection) { try { al.term.dispose(); } catch {} }
  if (al.onResize) window.removeEventListener('resize', al.onResize);
  // 3. 通知后端清容器（commit 路径已清，不重复）
  state.accLogin = null;
  if (alsoCloseModal) closeModal('#acc-modal');
  // 重置 step
  showAccStep('config');
  $('#acc-modal-stage').textContent = 'step 1 · configure';
  $('#acc-login-commit').disabled = false;
  if (!skipServerCancel && currentTab() === 'accounts') await renderAccounts();
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

/** 打开题目及两条业务补充编辑。@param {number|null} topicId 题目 ID。@returns {void} */
function openTopicModal(topicId) {
  const topic = topicId ? state.topics.find(t => t.id === topicId) : null;
  const form = $('#topic-form');
  form.reset();
  form.topic_id.value = topic ? topic.id : '';
  form.no.value = topic ? topic.no : nextTopicNo();
  form.title.value = topic ? topic.title : '';
  form.description.value = topic ? topic.description : '';
  form.followup_1.value = topic?.followups?.[0] || '';
  form.followup_2.value = topic?.followups?.[1] || '';
  form.category.value = topic ? topic.category : '';
  $('#topic-modal-title').textContent = topic ? `#${topic.no}` : 'new';
  $('#topic-delete').classList.toggle('hidden', !topic);
  openModal('#topic-modal');

  form.onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    const first = String(fd.get('followup_1') || '').trim();
    const second = String(fd.get('followup_2') || '').trim();
    if (second && !first) return alert('请先填写第一条补充需求');
    const body = {
      no: Number(fd.get('no')),
      title: fd.get('title'),
      description: fd.get('description') || '',
      category: fd.get('category') || '',
      enabled: true,
      followups: [first, second].filter(Boolean),
    };
    const submit = form.querySelector('button[type=submit]');
    submit.disabled = true;
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
    } finally {
      submit.disabled = false;
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
      <td><span class="pill pill-${b.status}">${escapeHTML(b.status === 'quota_wait' ? '额度等待' : b.status)}</span>${b.status === 'quota_wait' ? `<div class="warmup-error">${escapeHTML(b.quota_policy?.message || b.passive_quota?.message || '等待最新额度')}</div>` : ''}</td>
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
  const pauseButton = ['active', 'quota_wait'].includes(batch.status)
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

/**
 * 展示本次冻结需求与可核对的自动补充进度。
 * @param {Object} run 运行详情与补充状态。
 * @returns {string} 已转义的需求 HTML。
 */
function renderRunFollowups(run) {
  const plan = run.followups;
  const messages = Array.isArray(plan?.messages) ? plan.messages : [];
  const labels = { single: '单轮任务', not_started: '等待开始', awaiting: '当前轮执行中',
    pending: '补充投递待确认', complete: '全部轮次完成',
    unknown: '阶段状态待核对', invalid: '阶段证据无效，请查看运行错误' };
  const label = labels[plan?.phase] || '阶段状态待核对';
  const count = plan?.planned == null ? '未知' : `${plan.completed ?? '待确认'}/${plan.planned}`;
  const timed = plan?.mode === 'timed';
  const itemLabels = { scheduled: '等待到点', pending: '投递待确认', queued: '已入队，等待消费',
    consumed: '已消费，执行中', completed: '已完成', unknown: '状态待核对' };
  const warning = ['unknown', 'invalid'].includes(plan?.phase) ? `${label} · ` : '';
  const summary = timed ? `${warning}按时间投递 · 已投递 ${plan.delivered ?? '待确认'}/${plan.planned} · 已消费 ${plan.consumed ?? '待确认'}/${plan.planned}` : label;
  return `<p>${escapeHTML(summary)} · 已完成补充 ${escapeHTML(count)}</p>
    <details><summary>初始需求</summary><pre class="transcript-pre">${escapeHTML(run.prompt || '历史需求暂不可用')}</pre></details>
    ${messages.map((text, index) => {
      const offset = plan?.offsets_sec?.[index];
      const when = timed && Number.isInteger(offset) ? ` · 启动后 ${Math.floor(offset / 60)}分${offset % 60}秒` : '';
      const progress = timed ? ` · ${itemLabels[plan.items?.[index]] || '状态待核对'}` : '';
      return `<details><summary>补充 ${index + 1}${escapeHTML(when + progress)}</summary><pre class="transcript-pre">${escapeHTML(text)}</pre></details>`;
    }).join('')}`;
}

/** 创建运行详情容器。@param {string} rid 运行标识。@returns {void} */
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
      <h4>需求与自动补充</h4>
      <div id="run-detail-followups">等待运行计划</div>
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
      <h4 id="run-detail-error-title">错误</h4>
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
      <div class="stat-box"><div class="stat-label">权限模式</div><div class="stat-value-sm">${escapeHTML(capture.permission_mode || 'bypassPermissions')}</div></div>
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

/**
 * 按当前详情请求更新页面，保留既有异步生命周期。
 * @param {string} rid 运行标识。
 * @param {Object} run 运行详情。
 * @param {Array} files 产物列表。
 * @param {Object} stats 统计。
 * @param {string} transcript 终端输出。
 * @param {string} transcriptState 输出读取状态。
 * @param {Object} capture 抓包摘要。
 * @returns {void}
 */
function updateRunDetailContent(rid, run, files, stats, transcript, transcriptState, capture) {
  const detail = state.runDetail;
  if (!detail?.rendered) renderRunDetailShell(rid);
  const safeStatus = escapeHTML(run.status);
  setRunDetailText('#run-detail-followups', renderRunFollowups(run));

  const statusEl = $('#run-detail-status');
  if (statusEl) {
    const nextClass = `pill pill-${safeStatus}`;
    if (statusEl.className !== nextClass) statusEl.className = nextClass;
    const label = run.status === 'quota_wait' ? '额度等待' : run.status;
    if (statusEl.textContent !== label) statusEl.textContent = label;
  }

  setRunDetailText('[data-stat-key="tokens_in"]', renderStatValue(stats, 'tokens_in'));
  setRunDetailText('[data-stat-key="tokens_out"]', renderStatValue(stats, 'tokens_out'));
  setRunDetailText('[data-stat-key="requests"]', renderStatValue(stats, 'requests'));
  setRunDetailText('[data-stat-key="exit_code"]', escapeHTML(run.exit_code ?? '-'));
  setRunDetailText('[data-stat-key="claude_code_version"]', escapeHTML(run.claude_code_version || '-'));
  setRunDetailText('[data-stat-key="claude_effort_level"]', escapeHTML(run.claude_effort_level || '-'));
  const executionModel = run.execution_model ?? run.capture_model_override;
  setRunDetailText('[data-stat-key="model_override"]', executionModel ? escapeHTML(executionModel) : '<span class="muted">默认</span>');

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
    const waiting = run.status === 'quota_wait';
    $('#run-detail-error-title').textContent = waiting ? '额度等待' : '错误';
    const message = waiting ? `${run.error || '额度等待'}\n${run.quota_resume_at ? `恢复机会 ${formatWarmupTime(run.quota_resume_at)}` : '暂无可信恢复时间'}\n观察于 ${formatWarmupTime(run.passive_quota?.observed_at)}` : run.error;
    if (message && errorPre.textContent !== message) errorPre.textContent = message;
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
  state.runsEventSource = new EventSource(RUNTIME_BASE + '/api/runs-stream');
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
      permission_mode: fd.get('permission_mode') || 'bypassPermissions',
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
      form.permission_mode.value = 'bypassPermissions';
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
    const dur = r.status === 'quota_wait' ? (r.quota_resume_at ? `恢复 ${formatWarmupTime(r.quota_resume_at)}` : '等待可信恢复时间') : (r.started_at && r.ended_at) ? `${(r.ended_at - r.started_at).toFixed(0)}s` :
                (r.started_at ? `${(Date.now()/1000 - r.started_at).toFixed(0)}s` : '-');
    const terminal = ['success', 'failed', 'timeout', 'stopped', 'auth_failed'].includes(r.status);
    return `
      <tr>
        <td><code>${r.id}</code></td>
        <td>${tname}${kind}</td>
        <td>${escapeHTML(accMap[r.account_id] || `acc#${r.account_id}`)}</td>
        <td><span class="pill pill-${r.status}" title="${escapeHTML(r.status === 'quota_wait' ? r.quota_policy?.message || r.error || '额度等待' : '')}">${escapeHTML(r.status === 'quota_wait' ? '额度等待' : r.status)}</span></td>
        <td>${dur}</td>
        <td>${r.exit_code ?? '-'}</td>
        <td><div class="op-actions run-actions">
          <button class="btn btn-sm" data-detail="${r.id}">详情</button>
          ${['queued', 'running', 'quota_wait'].includes(r.status) ? `<button class="btn btn-sm btn-danger" data-stop="${r.id}">停止</button>` : ''}
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
  return ['queued', 'running', 'stopping', 'quota_wait'].includes(status);
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
    const r = await fetch(RUNTIME_BASE + `/api/runs/${rid}/transcript`, { credentials: 'same-origin' });
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
  const current = state.continueRun = {
    sid: resp.session_id,
    runId: rid,
  };
  $('#continue-run-id').textContent = rid;
  $('#continue-session-id').textContent = resp.claude_session_id || '-';
  $('#continue-modal-title').textContent = rid;
  $('#continue-quota-status').textContent = resp.status === 'quota_wait' ? resp.quota?.message || '额度等待' : '可继续输入';
  openModal('#continue-modal');
  const termState = await attachTerminal('#continue-xterm', resp.ws_path, resp.status || 'running');
  if (state.continueRun !== current) {
    termState.ws.close();
    termState.term.dispose();
    window.removeEventListener('resize', termState.onResize);
    return;
  }
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
    const r = await fetch(RUNTIME_BASE + '/api/auth/me', { credentials: 'same-origin' });
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
        const r = await fetch(RUNTIME_BASE + '/api/auth/login', {
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
    if (RUNTIME_BASE) { logoutBtn.style.display = 'none'; return; }
    logoutBtn.onclick = async (e) => {
      e.stopPropagation();
      if (!confirm('退出登录?')) return;
      try {
        await fetch(RUNTIME_BASE + '/api/auth/logout', { method: 'POST', credentials: 'same-origin' });
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
