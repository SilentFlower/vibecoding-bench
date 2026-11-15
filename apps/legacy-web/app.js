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
      const error = new Error(RUNTIME_BASE ? '统一后台会话已过期，请重新进入环境或任务页面' : 'auth required');
      error.status = 401;
      throw error;
    }
    if (!r.ok) {
      let msg = `${r.status} ${r.statusText}`;
      try { const j = await r.json(); msg = j.detail || j.error || msg; } catch {}
      const error = new Error(msg);
      error.status = r.status;
      throw error;
    }
    return r.json();
  });

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

/**
 * 增量更新已经转义的展示模板，保留控件、滚动容器和独立编辑宿主。
 * @param {Element} target 当前展示容器。
 * @param {string} html 已经过原模板转义的HTML。
 * @return {void}
 */
function patchRuntimeContent(target, html) {
  const template = document.createElement('template');
  template.innerHTML = html;
  const key = node => node.nodeType === Node.ELEMENT_NODE
    ? node.getAttribute('id') || node.getAttribute('data-runtime-key') || node.getAttribute('data-env-details') || node.getAttribute('data-workspace-section') : null;
  const compatible = (left, right) => left.nodeType === right.nodeType && left.nodeName === right.nodeName && key(left) === key(right);
  const patchChildren = (parent, desired) => {
    let cursor = parent.firstChild;
    for (const next of [...desired.childNodes]) {
      let node = cursor;
      if (!node || !compatible(node, next)) {
        node = null;
        for (let candidate = cursor; candidate; candidate = candidate.nextSibling) {
          if (compatible(candidate, next)) { node = candidate; break; }
        }
        if (!node) { parent.insertBefore(next.cloneNode(true), cursor); continue; }
        parent.insertBefore(node, cursor);
      }
      if (node.nodeType === Node.TEXT_NODE || node.nodeType === Node.COMMENT_NODE) {
        if (node.nodeValue !== next.nodeValue) node.nodeValue = next.nodeValue;
      } else if (!node.hasAttribute('data-runtime-preserve')) {
        for (const attribute of [...node.attributes]) {
          if (!next.hasAttribute(attribute.name) && !['data-active-scroll', 'open'].includes(attribute.name)) node.removeAttribute(attribute.name);
        }
        for (const attribute of [...next.attributes]) {
          if (node.getAttribute(attribute.name) !== attribute.value) node.setAttribute(attribute.name, attribute.value);
        }
        patchChildren(node, next);
      }
      cursor = node.nextSibling;
    }
    while (cursor) { const next = cursor.nextSibling; cursor.remove(); cursor = next; }
  };
  patchChildren(target, template.content);
}

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
  runtimeSettingsSaving: null,
  claudeCodeVersion: null,
  pendingTopicId: null,
  topicFilter: '',
  accountQuery: '',
  batchQuery: '',
  runQuery: '',
  runStatus: 'all',
  runsEventSource: null,
  runDetail: null,
  viewGeneration: 0,
  runWindowConfig: null,
  cliSettings: null,
  workCapture: null,
  environmentUI: {rows: [], query: '', status: 'all', expanded: new Set(), pending: new Set(),
    feedback: new Map(), kernelReleases: new Map(), checkingReleases: new Set(), request: 0, timer: null, loaded: false},
  kernelDialog: null,
  captureDialog: null,
};

// ===================== Pi 项目指挥 =====================
/**
 * 从 URL 读取明确选择的账号，非法值保留未选择状态，避免静默改用其他账号。
 * @return {number|null} 正整数账号、无参数 null，或无效参数 0。
 */
function iterationAccount() {
  const query = location.hash.indexOf('?');
  const values = new URLSearchParams(query < 0 ? '' : location.hash.slice(query + 1)).getAll('account');
  if (!values.length) return null;
  const id = Number(values[0]);
  return values.length === 1 && /^[1-9]\d*$/.test(values[0]) && Number.isSafeInteger(id) ? id : 0;
}

/**
 * 生成兼容旧路由的空间地址；0 表示明确保持未选择。
 * @param {string} mode 项目或养号路由。
 * @param {number|null} accountId 明确选择的账号。
 * @return {string} 当前页面内地址。
 */
function iterationUrl(mode, accountId) {
  return `#${mode}${accountId == null ? '' : `?account=${accountId}`}`;
}

/** 展示当前 URL 指定的独立工程空间。@return {Promise<void>} 页面加载完成。 */
function renderProjects() {
  const mode = currentTab(), generation = state.viewGeneration;
  const accountId = iterationAccount();
  const updateLinks = id => $$('[data-iteration-mode]').forEach(link => {
    link.href = iterationUrl(link.dataset.iterationMode, id);
    if (link.dataset.iterationMode === mode) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  });
  updateLinks(accountId);
  return window.ProjectsUI.mount({api: API, prefix: RUNTIME_BASE, namespace: mode, accountId,
    configureCli: openCliSettingsConfig, showCapture: openWorkCapture, closePanels: closeProjectDialogs,
    onAccountChange: id => {
      if (generation !== state.viewGeneration || currentTab() !== mode) return;
      // 选择账号只更新地址，不重建组件；切空间继续使用正常浏览历史。
      history.replaceState(history.state, '', iterationUrl(mode, id ?? 0));
      updateLinks(id ?? 0);
      syncRuntimeNavigation(location.hash, true);
    }});
}

/**
 * 从账号入口只读进入独立养号工程现场，不隐式启动或恢复 Pi。
 * @param {number} accountId 要查看的账号。
 * @return {void}
 */
function openWarmupAccount(accountId) {
  const target = iterationUrl('warmup', accountId);
  if (location.hash === target) navigate();
  else navigateTo(target);
}

// ===================== 路由 =====================
const ROUTES = {
  projects: renderProjects,
  environments: renderEnvironments,
  accounts: renderAccounts,
  topics: renderTopics,
  tasks: renderTasks,
  runs: renderRuns,
  warmup: renderProjects,
};

/** 读取 hash 中的页面名，查询参数不参与路由匹配。@return {string} 有效页面名。 */
function currentTab() {
  const hash = (location.hash || '#accounts').replace(/^#/, '').split('?')[0];
  return ROUTES[hash] ? hash : 'accounts';
}

/** 同源嵌入时同步受控导航参数至主后台。
 * @param {string} hash 目标内部路由。
 * @param {boolean} replace 是否替换当前筛选地址。
 * @return {boolean} 是否交由主后台导航。
 */
function syncRuntimeNavigation(hash = location.hash, replace = false) {
  const embedded = new URLSearchParams(location.search).get('view');
  if (!RUNTIME_BASE || window.parent === window || !['environments', 'tasks'].includes(embedded)) return false;
  const tab = hash.replace(/^#/, '').split('?')[0], query = new URLSearchParams(hash.split('?')[1] || '');
  // 重复账号参数保持无效选择，不能经父路由同步悄悄变成第一个账号。
  const account = query.getAll('account').length > 1 ? '0' : query.get('account');
  if (!Object.hasOwn(ROUTES, tab)) return false;
  const target = new URL(tab === 'environments' ? '/environments' : '/tasks', location.origin);
  if (!['environments', 'accounts'].includes(tab)) target.searchParams.set('tab', tab);
  for (const key of ['account', 'environment', 'gateway_account', 'section']) {
    if (query.has(key)) target.searchParams.set(key, key === 'account' ? account : query.get(key));
  }
  // 初次进入与父地址相同，避免 iframe 加载和顶层导航相互触发。
  if (target.pathname + target.search === window.parent.location.pathname + window.parent.location.search) return false;
  window.parent.postMessage({type: 'runtime:navigate', tab, replace,
    account, environment: query.get('environment'), gateway_account: query.get('gateway_account'), section: query.get('section')}, location.origin);
  return true;
}

/** 统一程序化跳转，嵌入时只由顶层写入历史。@param {string} hash 目标内部地址。@return {void} */
function navigateTo(hash) {
  if (!syncRuntimeNavigation(hash)) location.hash = hash;
}

// 由顶层路由创建唯一历史项，避免一次点击同时写入 iframe 和主页面历史。
document.addEventListener('click', event => {
  const link = event.target.closest('a[href^="#"]');
  if (link && !event.defaultPrevented && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey
      && event.button === 0 && syncRuntimeNavigation(link.getAttribute('href'))) event.preventDefault();
});

/** 切换视图并使旧页面、时段弹窗的异步回调失效。@return {void} */
async function navigate() {
  state.viewGeneration += 1;
  const generation = state.viewGeneration;
  const tab = currentTab();
  // 文档会跨二级导航保留，旧页面的窗口与详情刷新必须显式收口。
  endRunDetail();
  for (const selector of ['#modal', '#cc2api-binding-modal', '#warmup-modal', '#topic-modal', '#task-modal', '#batch-create-modal', '#runtime-settings-modal', '#runtime-capture-modal', '#runtime-confirm-modal']) closeModal(selector);
  leaveEnvironments();
  closeRunWindowConfig(true);
  closeProjectDialogs();
  window.ProjectsUI.unmount();
  const embedded = new URLSearchParams(location.search).get('view');
  document.documentElement.classList.toggle('embedded-environments', !!RUNTIME_BASE && embedded === 'environments');
  document.documentElement.classList.toggle('embedded-tasks', !!RUNTIME_BASE && embedded === 'tasks');
  syncRuntimeNavigation();
  document.documentElement.classList.toggle('environment-page', tab === 'environments');
  document.body.classList.toggle('work-console', tab !== 'environments');
  $$('.tabs a').forEach(a => a.classList.toggle('active', a.dataset.tab === tab));
  const view = $('#view');
  view.innerHTML = '';
  // 两个空间共用 DOM 结构；组件每次挂载都会清理上一个空间的订阅、选择和分页。
  const tpl = $(`#tpl-${tab === 'warmup' ? 'projects' : tab}`);
  if (tpl) view.appendChild(tpl.content.cloneNode(true));

  // 切换页面时关掉运行流
  if (tab !== 'runs' && state.runsEventSource) {
    state.runsEventSource.close();
    state.runsEventSource = null;
  }
  try {
    await Promise.all([ROUTES[tab](), document.fonts.ready]);
  } catch (error) {
    if (generation === state.viewGeneration) notifyRuntime('工作区读取失败：' + error.message);
  } finally {
    // 首屏与字体一起就绪后显示嵌入文档，避免依次展示空模板和字体回退。
    if (generation === state.viewGeneration && window.parent !== window) window.parent.postMessage({type:'runtime:ready'},location.origin);
  }
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
  if (account.warmup_engine === 'projects') {
    const project = account.project_pi, schedule = project?.schedule, work = project?.work;
    const names = {off: '未启动', running: 'Pi 指挥中', waiting: '等待执行条件', paused: '已暂停',
      blocked: '需要处理', ready: '待开始', verifying: '独立验收中', passed: '验收通过', stopped: '已停止'};
    const status = project?.status;
    const statusClass = project?.controller_active ? 'pill-running'
      : status === 'blocked' ? 'pill-failed' : status === 'waiting' ? 'pill-quota_wait' : 'pill-queued';
    const interval = schedule?.interval_max_minutes > schedule?.interval_minutes
      ? `${schedule.interval_minutes}～${schedule.interval_max_minutes} 分钟随机` : `${schedule?.interval_minutes} 分钟`;
    // 账号入口使用独立养号工程的实际计划，旧 worker 开关不能覆盖它的运行状态。
    return `<span class="pill ${statusClass}">${escapeHTML(project ? names[status] || status : '尚未配置项目池')}</span>
      <div>${schedule?.enabled ? `养号计划 · 每轮结束后间隔 ${escapeHTML(interval)}` : '养号自动计划未开启'}</div>
      <div class="muted">next ${escapeHTML(formatWarmupTime(schedule?.next_run_at))}</div>
      ${work ? `<div>${escapeHTML(work.project_key)} · ${escapeHTML(work.objective_id)}</div>` : ''}
      ${project?.message || schedule?.message ? `<div class="hint">${escapeHTML(project.message || schedule.message)}</div>` : ''}
      ${thresholds ? `<div class="muted">工程任务阈值：${escapeHTML(thresholds)}</div>` : ''}
      ${quotaStatuses}`;
  }
  if (account.cc2api_account_id == null && !Number(account.warmup_enabled || 0)) {
    return `<span class="pill pill-queued">${account.warmup_engine === 'pi' ? 'Pi 养号未开启' : '未绑定'}</span>
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
    waiting: 'pill-quota_wait',
    blocked: 'pill-failed',
    completed: 'pill-success',
  }[status] || (enabled ? 'pill-success' : 'pill-queued');
  const error = account.warmup_last_error
    ? `<div class="warmup-error" title="${escapeHTML(account.warmup_last_error)}">${escapeHTML(account.warmup_last_error)}</div>`
    : '';
  return `
    <div><code>${account.cc2api_account_id == null ? '本地 CLI' : `网关 #${escapeHTML(account.cc2api_account_id)}`}</code> <span class="pill ${statusClass}">${escapeHTML(status === 'quota_wait' ? '额度等待' : status)}</span></div>
    <div>${escapeHTML(account.warmup_interval_min_hours || 3)}-${escapeHTML(account.warmup_interval_max_hours || 5)}h</div>
    <div class="muted">next ${escapeHTML(formatWarmupTime(account.warmup_next_run_at))}</div>
    ${thresholds ? `<div class="muted">普通任务 / 养号阈值：${escapeHTML(thresholds)}</div>` : ''}
    ${quotaStatuses}
    ${error}
  `;
}

/** 代理归属仍由关联的网关账号管理；独立账号沿原授权配置流程处理。@param {number} id 任务账号。@return {void} */
function openAccountProxyConfig(id) {
 const account=state.accounts.find(item=>item.id===id);if(!account)return;
 if(account.cc2api_account_id!=null && RUNTIME_BASE){
  if(window.parent!==window)window.parent.postMessage({type:'runtime:account-edit',id:account.cc2api_account_id},location.origin);
  else location.href='/?account='+encodeURIComponent(account.cc2api_account_id);
  return;
 }
 openAccLoginModal(account);
}

/** 任务显示名称独立于配置目录标识。@param {object} account 公开账号。@return {string} 界面名称。 */
function accountDisplayName(account){return account?.display_name || account?.name || ''; }

/** 绘制定稿图标。@param {string} name 白名单符号名。@return {string} 图标。 */
function runtimeIcon(name){return `<svg class="runtime-icon" aria-hidden="true"><use href="approved-icons.svg#i-${name}"></use></svg>`;}
/** 展示真实状态，保持状态枚举与业务控制分离。@param {object} row 运行或批次。@return {string} 状态标记。 */
function runtimeBadge(row){const value=row.status,labels={running:'执行中',active:'执行中',success:'成功',passed:'已通过',queued:'排队中',quota_wait:'额度等待',stopping:'停止中',paused:'已暂停',failed:'失败',auth_failed:'授权异常',sync_failed:'同步异常',stopped:'已停止',timeout:'超时'};const label=row.run_window?.allowed===false?runStatusLabel(row):labels[value]||value;return `<span class="work-badge ${['running','active','success','passed'].includes(value)?'good':['failed','auth_failed','timeout','quota_wait'].includes(value)?'warning':''}" data-status="${escapeHTML(value)}"><i></i>${escapeHTML(label)}</span>`;}
/** 保留卡片DOM与草稿，只切换当前搜索结果。@return {void} */
function filterTaskAccountCards(){const query=state.accountQuery.trim().toLocaleLowerCase();$$('[data-work-account-card]',$('#accounts-body')).forEach(card=>{card.hidden=!!query&&!`${card.textContent} ${card.dataset.workAccountCard}`.toLocaleLowerCase().includes(query);});}

/**
 * 分别载入正式账号与登录草稿，只有正式账号进入共享任务选择状态。
 * @return {Promise<void>} 账号列表与操作入口就绪
 */
async function renderAccounts() {
  if (currentTab() !== 'accounts') return;
  const generation = state.viewGeneration;
  try {
    const [accounts, loginDrafts] = await Promise.all([API('/accounts'), API('/accounts/login-drafts', { cache: 'no-store' })]);
    // 请求期间可能已切页，旧列表不能写入新视图或覆盖新一轮页面状态。
    if (currentTab() !== 'accounts' || generation !== state.viewGeneration) return;
    [state.accounts, state.loginDrafts] = [accounts, loginDrafts];
  } catch (e) {
    if (currentTab() === 'accounts' && generation === state.viewGeneration) notifyRuntime('加载账号失败: ' + e.message);
    return;
  }

  const body = $('#accounts-body');
  const search=$('#work-account-search');search.value=state.accountQuery;search.oninput=()=>{state.accountQuery=search.value;filterTaskAccountCards();};
  const loginResult = $('#account-login-result');
  loginResult.textContent = state.accountLoginMessage;
  loginResult.classList.toggle('hidden', !state.accountLoginMessage);
  body.innerHTML = state.accounts.map(a => {
    const bound=a.cc2api_account_id!=null,worker=a.warmup_engine!=='projects';
    const workerAction=Number(a.warmup_enabled||0)===1?`<button type="button" data-warmup-now="${a.id}">立即运行养号 ${runtimeIcon('play')}</button>`:(bound||a.warmup_last_status==='paused')?`<button type="button" data-warmup-resume="${a.id}">恢复养号 ${runtimeIcon('play')}</button>`:`<button type="button" data-warmup-config="${a.id}">配置养号 ${runtimeIcon('arrow')}</button>`;
    const message=a.passive_quota?.account_error?a.passive_quota.message:a.passive_quota?.source==='manual'?'额度已手动更新。':bound?'重新授权提交后，同步更新关联账号的凭据。':'从已有网关账号关联，或创建新的网关账号。';
    return `<article class="work-panel work-account" data-work-account-card="${a.id}">
      <header><span class="initial">${runtimeIcon('users')}</span><div><h3><button type="button" class="work-title-button" data-account-details="${a.id}">${escapeHTML(accountDisplayName(a))}</button></h3><small>任务账号 #${a.id}</small></div><span class="work-badge ${a.enabled?'good':''}">${a.enabled?'已启用':'已停用'}</span></header>
      <div class="work-proxy-row"><span class="work-proxy-compact">${runtimeIcon('globe')}<span class="work-proxy-name">${a.upstream_socks5_host?renderProxyEndpoint(a):'直连'}</span></span><button type="button" class="work-proxy-switch" data-proxy-config="${a.id}">${bound?'切换代理':'配置代理与授权'}</button></div>
      <div class="work-condition"><span>网关关联</span><strong>${bound?'网关账号 #'+escapeHTML(a.cc2api_account_id):'尚未关联'}</strong></div>
      <div class="work-condition"><span>环境时区</span><strong>${escapeHTML(a.effective_timezone||a.timezone||'未提供')}</strong></div>
      <div class="work-condition"><span>Claude Code</span><strong>${escapeHTML(a.claude_code_version||'继承全局')}</strong></div>
      <div class="work-account-links"><a href="#projects?account=${a.id}">工程迭代 ${runtimeIcon('arrow')}</a>${worker?workerAction:`<a href="#warmup?account=${a.id}">Pi 养号 ${runtimeIcon('arrow')}</a>`}</div>
      <section class="work-gateway-actions" aria-label="${escapeHTML(accountDisplayName(a))}的网关账号操作"><div class="work-gateway-heading"><span>${runtimeIcon('key')}网关账号</span><strong>${bound?'#'+escapeHTML(a.cc2api_account_id):'尚未关联'}</strong></div><div class="work-gateway-buttons">${!bound?`<button type="button" class="btn btn-sm" data-cc2-create="${a.id}">${runtimeIcon('plus')}创建网关账号</button><button type="button" class="btn btn-sm" data-cc2-bind="${a.id}">关联已有账号</button>`:''}${!bound||RUNTIME_BASE?`<button type="button" class="btn btn-sm" data-relogin="${a.id}">${runtimeIcon('key')}${bound?'重新授权并同步':'重新授权'}</button>`:''}${bound?`<button type="button" class="btn btn-sm btn-danger danger" data-cc2-unbind="${a.id}">解绑</button>`:''}${a.credential_ownership?.phase&&a.credential_ownership.phase!=='ready'?'<a class="btn btn-sm" href="#environments">凭据交接对账</a>':''}</div><p role="status">${escapeHTML(message||'')}</p></section>
      <footer><button type="button" class="btn btn-sm" data-cli-settings="${a.id}">CLI 配置</button><button type="button" class="btn btn-sm" data-quota="${a.id}">额度</button><button type="button" class="btn btn-sm" data-warmup-config="${a.id}">养号 / 额度设置</button>${RUNTIME_BASE?`<button type="button" class="btn btn-sm" data-run-window-config="${a.id}">运行时段</button>`:''}<button type="button" class="btn btn-sm btn-danger danger" data-del="${a.id}">删除</button></footer>
    </article>`;
  }).join('') || '<div class="work-empty"><h3>暂无任务账号</h3><p>添加账号后可以授权并开始任务。</p></div>';
  const drafts=$('#work-login-drafts');drafts.hidden=!state.loginDrafts.length;
  drafts.innerHTML='<header><h3>未完成的登录</h3><span>'+state.loginDrafts.length+' 个草稿</span></header>'+(state.loginDrafts || []).map(draft => {
    const phase = { preparing: '准备登录', authorizing: '登录中 · 未提交', ready_to_submit: '认证通过 · 待提交', ended: '终端已结束',
      interrupted: '登录已中断', cancelled: '已取消 · 环境保留', submitting: '保存未完成 · 请继续提交', reconcile: '需检查 / 对账', deleting: '清理未完成 · 可重试' }[draft.state] || '未完成登录';
    const id = escapeHTML(draft.environment_id);
    return `<article class="work-history-row account-draft-row"><span class="initial">${runtimeIcon('key')}</span><div><strong>${escapeHTML(draft.name)}</strong><small>${escapeHTML(phase)}</small><small>${escapeHTML(draft.message || (draft.credentials_present && !draft.credentials_ready ? '保留授权产物；继续后检查认证状态' : '尚未保存账号'))}</small><small class="work-draft-network">${escapeHTML(draft.proxy_known ? (draft.proxy_summary || '未配置代理') : '配置待检查')} · 不参与任务与养号</small></div><div class="buttons account-actions">
        <button type="button" class="btn btn-sm" data-draft-resume="${id}" ${draft.can_resume ? '' : 'disabled'}>继续登录</button>
        <button type="button" class="btn btn-sm" data-draft-restart="${id}" ${draft.can_restart ? '' : 'disabled'}>重新登录</button>
        ${draft.session_id ? `<button type="button" class="btn btn-sm" data-draft-cancel="${id}" ${draft.can_restart ? '' : 'disabled'}>取消登录</button>` : ''}
        <button type="button" class="btn btn-sm btn-danger" data-draft-delete="${id}" ${draft.can_delete ? '' : 'disabled'}>删除草稿</button>
        ${draft.can_reconcile ? `<button type="button" class="btn btn-sm" data-draft-reconcile="${id}">恢复检查</button>` : ''}
        ${draft.state === 'reconcile' ? '<a class="btn btn-sm" href="#environments">查看环境</a>' : ''}
      </div></article>`;
  }).join('') || '<div class="work-empty"><h3>暂无任务账号</h3><p>添加账号后可以授权并开始任务。</p></div>';

  filterTaskAccountCards();

  drafts.onclick = body.onclick = async (e) => {
    if(e.target.dataset.accountDetails){const account=state.accounts.find(item=>String(item.id)===e.target.dataset.accountDetails);if(account){endRunDetail();$('#modal .modal-titlebar-name').textContent='账号详情';$('#modal-content').innerHTML=`<div class="work-dialog-content"><h2>账号详情 · ${escapeHTML(accountDisplayName(account))}</h2><p class="work-note">配置目录 ${escapeHTML(account.profile_path)}</p>${renderOauthTokenStatus(account)}${renderPassiveQuota(account.passive_quota)}${renderAccountTimezone(account)}${renderWarmupStatus(account)}${account.credential_ownership?`<p>${escapeHTML(account.credential_ownership.message)}</p>`:''}</div>`;$('#modal-content').onclick=body.onclick;openModal('#modal');}return;}
    if (e.target.dataset.proxyConfig) { await openAccountProxyConfig(Number(e.target.dataset.proxyConfig));return; }
    if (e.target.dataset.cliSettings) {
      await openCliSettingsConfig(Number(e.target.dataset.cliSettings));
      return;
    }
    const draftId = e.target.dataset.draftResume || e.target.dataset.draftRestart || e.target.dataset.draftCancel || e.target.dataset.draftDelete || e.target.dataset.draftReconcile;
    if (draftId) {
      const draft = state.loginDrafts.find(item => item.environment_id === draftId);
      if (!draft) return;
      if (e.target.dataset.draftDelete && !await confirmRuntimeAction(`删除未提交草稿「${draft.name}」？将取消登录，并删除专属容器、HOME、缓存及未提交授权产物。`)) return;
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
      } catch (error) { notifyRuntime('草稿操作未完成：' + error.message); }
      finally { await renderAccounts(); }
      return;
    }
    const id = e.target.dataset.del;
    const quotaId = e.target.dataset.quota;
    const reloginId = e.target.dataset.relogin;
    const createId = e.target.dataset.cc2Create;
    const bindId = e.target.dataset.cc2Bind;
    const processId = e.target.dataset.cc2Process;
    if (e.target.dataset.runWindowConfig) {
      try { await openRunWindowConfig(e.target.dataset.runWindowConfig); }
      catch (error) { notifyRuntime('载入运行时段失败：' + error.message); }
      return;
    }
    const warmupConfigId = e.target.dataset.warmupConfig;
    const warmupConsoleId = e.target.dataset.warmupConsole;
    const warmupNowId = e.target.dataset.warmupNow;
    const warmupResumeId = e.target.dataset.warmupResume;
    const unbindId = e.target.dataset.cc2Unbind;
    if (quotaId) {
      e.target.disabled = true;
      try {
        const quota = await API(`/accounts/${quotaId}/quota`, { method: 'POST' });
        if (currentTab() !== 'accounts' || generation !== state.viewGeneration) return;
        // 核验会更新服务端门禁，重新读取摘要，避免卡片继续显示上一次认证异常。
        await renderAccounts();
        if (currentTab() !== 'accounts' || generation !== state.viewGeneration) return;
        openQuotaDetail(quotaId, quota);
      } catch (err) {
        if (currentTab() === 'accounts' && generation === state.viewGeneration) notifyRuntime('查询额度失败: ' + err.message);
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
      catch (error) { notifyRuntime('加载可关联账号失败：' + error.message); }
      finally { e.target.disabled = false; }
      return;
    }
    if (createId || processId) {
      e.target.disabled = true;
      try {
        const result = await API(`/accounts/${createId || processId}/cc2api/${createId ? 'create' : 'process'}`, { method: 'POST' });
        state.accountLoginMessage = createId
          ? `已创建 网关账号 #${result.cc2api_account.id} 并完成关联`
          : `已更新 网关账号 #${result.cc2api_account_id} 的进程指标${result.canonical_process.observation?.sample_count ? '' : '；CLI RSS 尚未采集'}`;
        await renderAccounts();
        if (processId && state.cliSettings?.accountId === Number(processId)) {
          $('#cli-settings-feedback').classList.remove('is-error');
          $('#cli-settings-feedback').textContent = state.accountLoginMessage;
        }
      } catch (err) {
        notifyRuntime((createId ? '创建 网关账号失败：' : '更新进程指标失败：') + err.message);
      } finally {
        e.target.disabled = false;
      }
      return;
    }
    if (warmupConsoleId) {
      openWarmupAccount(Number(warmupConsoleId));
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
          notifyRuntime(result.warmup_last_error || `未启动：${result.warmup_last_status || '账号当前不可认领'}`);
        }
        await renderAccounts();
      } catch (err) {
        notifyRuntime('立即运行失败: ' + err.message);
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
        notifyRuntime('恢复养号失败: ' + err.message);
      } finally {
        e.target.disabled = false;
      }
      return;
    }
    if (unbindId && await confirmRuntimeAction(`解绑账号 #${unbindId} 的 网关账号并停止未来养号?`)) {
      e.target.disabled = true;
      try {
        await API(`/accounts/${unbindId}/cc2api-binding`, { method: 'DELETE' });
        await renderAccounts();
      } catch (err) {
        notifyRuntime('解绑失败: ' + err.message);
      } finally {
        e.target.disabled = false;
      }
      return;
    }
    if (id && await confirmRuntimeAction(`删除账号 #${id}?`)) {
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
    const host=$('#runtime-login-proxy');
    if(host.dataset.managed==='true'&&!$('#acc-use-manual').checked&&host.dataset.proxyDisabled!=='true'){
      const choice=host.dataset.proxyChoice;
      if(choice!==undefined||state.accLogin?.mode==='new'){
        const selected=choice?JSON.parse(choice):null;
        for(const key of Object.keys(body))if(key.startsWith('upstream_'))delete body[key];
        body.proxy_id=selected?.id??null;if(selected)body.proxy_revision=selected.revision;
      }
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
 * 独立选择已有 网关账号，关联动作不修改养号设置。
 * @param {Object} account 当前未关联的本地账号
 * @return {Promise<void>} 候选账号加载后显示窗口
 */
async function openCc2apiBindingModal(account) {
  const generation = state.viewGeneration;
  const accounts = await API('/cc2api/accounts');
  if (currentTab() !== 'accounts' || generation !== state.viewGeneration) return;
  state.cc2apiAccounts = accounts;
  const form = $('#cc2api-binding-form');
  form.account_id.value = account.id;
  const available = state.cc2apiAccounts.filter(item => !state.accounts.some(a =>
    a.cc2api_account_id != null && Number(a.cc2api_account_id) === Number(item.id)));
  form.cc2api_account_id.innerHTML = '<option value="">请选择已有账号</option>' + available.map(item =>
    `<option value="${escapeHTML(item.id)}">#${escapeHTML(item.id)} ${escapeHTML(item.name || 'OAuth')} · ${escapeHTML(item.email_masked || '-')}</option>`).join('');
  form.querySelector('button[type="submit"]').disabled = available.length === 0;
  $('#cc2api-binding-hint').textContent = available.length
    ? '关联会核对登录身份和设备，保留目标账号配置；不会创建账号或修改养号设置。'
    : '当前没有可关联的账号。可先在账号页创建 网关账号。';
  $('#cc2api-binding-title').textContent = `#${account.id} ${accountDisplayName(account)}`;
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
    state.accountLoginMessage = `已关联现有 网关账号 #${result.cc2api_account.id}，保留该账号原配置`;
    closeModal('#cc2api-binding-modal');
    await renderAccounts();
  } catch (error) { notifyRuntime('关联已有账号失败：' + error.message); }
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
  form.dataset.engine = account.warmup_engine || 'worker';
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
  $('#warmup-modal-title').textContent = `#${account.id} ${accountDisplayName(account)}`;
  openModal('#warmup-modal');
}

/**
 * 按工程或旧 worker 架构展示额度编辑和独立计划入口。
 * @param {HTMLFormElement} form 养号与额度配置表单
 * @return {void} 不返回值
 */
function updateWarmupBindingState(form) {
  const account = state.accounts.find(item => String(item.id) === String(form.account_id.value));
  const unified = account?.warmup_engine === 'projects';
  const bound = account?.cc2api_account_id != null;
  $('#warmup-legacy-interval').classList.toggle('hidden', unified);
  $('#warmup-legacy-enabled').classList.toggle('hidden', unified);
  for (const name of ['interval_min_hours', 'interval_max_hours']) {
    form.elements[name].disabled = unified;
    form.elements[name].required = !unified;
  }
  form.enabled.disabled = unified;
  const projectLink = $('#warmup-projects-link');
  projectLink.classList.toggle('hidden', !unified);
  projectLink.onclick = () => { closeModal('#warmup-modal'); openWarmupAccount(Number(form.account_id.value)); };
  $('#warmup-binding-hint').textContent = unified
    ? 'Pi 养号使用独立的工程现场、项目池、追加指南、预算和自动计划；此处只修改账号额度阈值。'
    : bound
    ? `定时养号使用已关联的 网关账号 #${account.cc2api_account_id}；此处只修改养号与额度设置。`
    : '使用此账号已有的 CLI OAuth 凭据，可独立启用定时养号与额度阈值。';
  $('#warmup-quota-policy-hint').textContent = unified
    ? '额度从正常响应中被动更新。命中阈值时由工程门禁暂停；保留原会话与累计预算，等待窗口重置或真实被动额度更新后继续。此处不修改养号工程计划，也不主动查询额度。'
    : '额度从正常响应中被动更新。观测到任一阈值命中时，当前普通任务或养号仍按原计划完成本轮（包括补充与收尾），下一轮等待窗口重置或真实额度更新，并遵守原投放间隔。单次响应仍可能跨过阈值。网关 API 转发不受此阈值控制。';
}

/**
 * 更新账号级阈值表单的可编辑状态及已用/剩余说明。
 * @param {HTMLFormElement} form 养号配置表单
 * @return {void} 不返回值
 */
function updateWarmupQuotaInputs(form) {
  const unified = form.dataset.engine === 'projects';
  for (const window of ['5h', '7d']) {
    const input = form.elements[`warmup_quota_${window}_limit_percent`];
    const enabled = form.elements[`quota_${window}_enabled`].checked;
    input.disabled = !enabled;
    input.required = enabled;
    input.closest('.field')?.classList.toggle('upgrade-disabled', !enabled);
    const value = Number(input.value);
    $(`#warmup-quota-${window}-hint`).textContent = !enabled ? '已关闭，沿用额度用满保护'
      : input.value && Number.isInteger(value) && value >= 1 && value <= 100
        ? unified ? `观测已用达到 ${value}%（剩余 ${100 - value}%）时工程额度门禁暂停，等待额度恢复`
          : `观测已用达到 ${value}%（剩余 ${100 - value}%）时当前普通任务与养号完成本轮，下一轮等待`
        : '请输入 1～100 的已用百分比整数';
  }
}

/**
 * 保存当前架构允许编辑的字段，关闭额度限制时显式提交 null。
 * @param {SubmitEvent} e 配置提交事件
 * @return {Promise<void>} 保存并刷新账号状态后完成
 */
async function saveWarmupConfig(e) {
  e.preventDefault();
  const form = e.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  const accountId = Number(form.account_id.value);
  const payload = {
    warmup_quota_5h_limit_percent: form.quota_5h_enabled.checked ? Number(form.warmup_quota_5h_limit_percent.value) : null,
    warmup_quota_7d_limit_percent: form.quota_7d_enabled.checked ? Number(form.warmup_quota_7d_limit_percent.value) : null,
  };
  // 养号工程计划由独立服务维护，提交旧 worker 开关会误改用户已保存的计划。
  if (form.dataset.engine !== 'projects') Object.assign(payload, {
    enabled: form.enabled.checked,
    interval_min_hours: Number(form.interval_min_hours.value),
    interval_max_hours: Number(form.interval_max_hours.value),
  });
  button.disabled = true;
  try {
    await API(`/accounts/${accountId}/warmup`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    });
    closeModal('#warmup-modal');
    await renderAccounts();
  } catch (err) {
    notifyRuntime('保存养号与额度配置失败: ' + err.message);
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

/**
 * 使用账号 IANA 时区显示指定时刻，时区无效时明确保留未知状态。
 * @param {number} timestamp UTC 秒
 * @param {string} zone IANA 时区
 * @return {string} 当地日期和时间
 */
function accountLocalTime(timestamp, zone) {
  if (!Number.isFinite(timestamp) || !zone) return '时区待核对';
  try {
    return new Intl.DateTimeFormat('zh-CN', {timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit',
      weekday: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false}).format(new Date(timestamp * 1000));
  } catch { return '时区待核对'; }
}

/**
 * 渲染服务端窗口状态，时钟沿用服务器时刻偏移，不作为执行许可。
 * @param {Object} account 含 id 和 run_window 的账号摘要
 * @return {string} 已转义的当地时间及运行窗口
 */
function renderAccountRunWindow(account) {
  const policy = account.run_window;
  if (!policy) return '';
  const now = Number(policy.server_now);
  const boundary = policy.next_open_at || policy.next_close_at || '';
  const opening = policy.next_open_at ? `下次开放 ${accountLocalTime(policy.next_open_at, policy.timezone)}`
    : policy.next_close_at ? `本时段结束 ${accountLocalTime(policy.next_close_at, policy.timezone)}` : '';
  return `<div class="run-window-display" data-run-window-account="${escapeHTML(account.id)}"
    data-clock-offset="${Number.isFinite(now) ? now * 1000 - Date.now() : 0}" data-refresh-at="${escapeHTML(boundary)}">
    <div data-local-clock="${escapeHTML(policy.timezone || '')}">${escapeHTML(accountLocalTime(now, policy.timezone))}</div>
    <div class="muted" data-beijing-clock>北京时间 ${escapeHTML(accountLocalTime(now, 'Asia/Shanghai'))}</div>
    <div>${escapeHTML(policy.message)}</div><div class="muted">${escapeHTML(opening)}</div>
  </div>`;
}

/**
 * 更新当地时钟，并仅在服务端给出的下一边界重新读取窗口状态。
 * @return {void} 不重绘表单，不发送模型或额度查询
 */
function tickAccountRunWindows() {
  $$('[data-run-window-account]').forEach(node => {
    const now = (Date.now() + Number(node.dataset.clockOffset || 0)) / 1000;
    const local = $('[data-local-clock]', node);
    if (local) local.textContent = accountLocalTime(now, local.dataset.localClock);
    const beijing = $('[data-beijing-clock]', node);
    if (beijing) beijing.textContent = '北京时间 ' + accountLocalTime(now, 'Asia/Shanghai');
    if (node.dataset.refreshAt && now >= Number(node.dataset.refreshAt)) {
      node.dataset.refreshAt = '';
      API(`/accounts/${encodeURIComponent(node.dataset.runWindowAccount)}/run-window`).then(policy => {
        if (node.isConnected) node.outerHTML = renderAccountRunWindow({id: node.dataset.runWindowAccount, run_window: policy});
      }).catch(() => {
        if (node.isConnected) node.append(document.createTextNode(' 状态更新失败，请刷新页面'));
      });
    }
  });
}

/**
 * 显示每项等待的实际原因，已开始的运行不被标为休息。
 * @param {Object} record run 或批次摘要
 * @return {string} 用户可见状态
 */
function runStatusLabel(record) {
  if (['queued', 'active', 'quota_wait'].includes(record.status) && record.run_window?.allowed === false) {
    return record.status === 'quota_wait' ? '额度及时段等待' : '时段等待';
  }
  return record.status === 'quota_wait' ? '额度等待' : record.status;
}

/**
 * 构造可增删的当地时间区间，输入始终由服务器严格校验。
 * @param {Object} interval 起止时间
 * @return {string} 已转义的输入行
 */
function runWindowIntervalRow(interval = {start: '09:00', end: '18:00'}) {
  return `<div class="run-window-interval"><label class="field"><span class="lbl">开始时间</span><input type="time" data-window-start value="${escapeHTML(interval.start)}" required></label>
    <label class="field"><span class="lbl">结束时间</span><input type="time" data-window-end value="${escapeHTML(interval.end)}" required></label>
    <button type="button" class="btn btn-sm" data-window-remove>移除</button></div>`;
}

/**
 * 关闭时保留输入，只禁用时间配置，避免无效的必填控件阻挡关闭限制。
 * @return {void}
 */
function updateRunWindowForm() {
  const enabled = $('#run-window-form').elements.enabled.checked;
  $('#run-window-options').disabled = !enabled;
  $('#run-window-summary').textContent = enabled
    ? '仅在选中的星期与时间段开始新任务，使用上方环境时区。'
    : '当前不限制开始时间，可全天开始新任务；保存时保留原有星期和时间段。';
}

/**
 * 加载并打开账号时段配置，表单不提供另一个调度时区。
 * @param {string|number} aid 账号标识
 * @return {Promise<void>} 完成表单初始化
 */
async function openRunWindowConfig(aid) {
  if(window.nativeEnvironmentWorkspace){window.nativeEnvironmentWorkspace(Number(aid));return;}
  if(state.runWindowConfig?.sending)return;
  $('#run-window-form').onsubmit = saveRunWindowConfig;
  $('#run-window-form').elements.enabled.onchange = updateRunWindowForm;
  $('#run-window-add').onclick = () => {
    if ($$('.run-window-interval', $('#run-window-form')).length >= 8) return;
    $('#run-window-intervals').insertAdjacentHTML('beforeend', runWindowIntervalRow());
  };
  $('#run-window-intervals').onclick = event => {
    if (event.target.hasAttribute('data-window-remove')) event.target.closest('.run-window-interval').remove();
  };
  closeModal('#run-window-modal');
  const inline=!!environmentWorkspace && state.environmentUI.rows.find(row=>row.environment_id===environmentWorkspace.id)?.account_id===Number(aid);
  const request = {accountId: aid, inline, sending:false};
  state.runWindowConfig = request;
  let policy;
  try {
    policy = await API(`/accounts/${encodeURIComponent(aid)}/run-window`);
  } catch (error) {
    if (state.runWindowConfig === request) throw error;
    return;
  }
  // 最后一次打开操作拥有弹窗，迟到的响应不能换掉当前账号。
  if (state.runWindowConfig !== request) return;
  const config = policy.config || {enabled: false, days: [], intervals: []};
  const form = $('#run-window-form');
  form.elements.account_id.value = aid;
  form.elements.enabled.checked = config.enabled;
  form.dataset.savedWindowConfig = JSON.stringify(config);
  $('#run-window-timezone').textContent = policy.timezone || '时区待核对';
  $('#run-window-days').innerHTML = ['一', '二', '三', '四', '五', '六', '日'].map((day, index) =>
    `<label><input type="checkbox" data-window-day value="${index}" ${config.days.includes(index) ? 'checked' : ''}>周${day}</label>`).join('');
  $('#run-window-intervals').innerHTML = (config.intervals.length ? config.intervals : [{start: '09:00', end: '18:00'}]).map(runWindowIntervalRow).join('');
  updateRunWindowForm();
  if(inline){const host=$('#environment-schedule-editor');if(host){host.replaceChildren(form);host.closest('[data-section-body]').classList.add('editing');}else closeRunWindowConfig(true);}
  else openModal('#run-window-modal');
}

/** 结束时段编辑并归还唯一共享表单。@param {boolean} force 导航强制关闭。@return {boolean} 是否关闭。 */
function closeRunWindowConfig(force=false){
  const request=state.runWindowConfig;if(request?.sending&&!force)return false;
  state.runWindowConfig=null;const form=$('#run-window-form');
  if(request?.inline){$('#run-window-modal .modal-card').append(form);$('#environment-schedule-editor')?.closest('[data-section-body]')?.classList.remove('editing');}
  $('button[type=submit]',form).disabled=false;$('#run-window-modal').classList.add('hidden');return true;
}

/**
 * 保存账号运行时间段，服务端只改变后续入场规则。
 * @param {SubmitEvent} event 表单事件
 * @return {Promise<void>} 保存并刷新当前列表
 */
async function saveRunWindowConfig(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const submit = $('button[type="submit"]', form);
  const request = state.runWindowConfig;
  if (!request || submit.disabled || (!request.inline && $('#run-window-modal').classList.contains('hidden'))) return;
  submit.disabled = true;request.sending=true;
  try {
    const enabled = form.elements.enabled.checked;
    // 关闭限制不应被尚未完成的编辑阻拦，也不能把已保存的配置清空。
    const config = enabled ? {
      days: $$('[data-window-day]:checked', form).map(input => Number(input.value)),
      intervals: $$('.run-window-interval', form).map(row => ({start: $('[data-window-start]', row).value, end: $('[data-window-end]', row).value})),
    } : JSON.parse(form.dataset.savedWindowConfig);
    await API(`/accounts/${encodeURIComponent(request.accountId)}/run-window`, {method: 'PUT', body: JSON.stringify({
      enabled, days: config.days, intervals: config.intervals,
    })});
    // 保存仍会落到原账号；关窗、切页或另开账号后不再操作共享弹窗。
    if (state.runWindowConfig !== request) return;
    if (currentTab() === 'environments') await renderEnvironments();
    else if (currentTab() === 'accounts') await renderAccounts();
    if (state.runWindowConfig === request) {
      if(request.inline){form.dataset.savedWindowConfig=JSON.stringify({enabled,days:config.days,intervals:config.intervals});notifyRuntime('运行时段已保存');}
      else {request.sending=false;closeModal('#run-window-modal');}
    }
  } catch (error) {
    if (state.runWindowConfig === request) notifyRuntime('保存运行时段失败：' + error.message);
  } finally {
    if (state.runWindowConfig === request) {request.sending=false;submit.disabled=false;}
  }
}

/**
 * 展示环境已生效时区及当地运行窗口。
 * @param {Object} account 账号摘要
 * @return {string} 已转义的时区信息
 */
function renderAccountTimezone(account) {
  const timezone = account.effective_timezone || account.timezone || '-';
  const mode = account.timezone_mode === 'manual' ? 'manual' : 'auto';
  return `
    <code>${escapeHTML(timezone)}</code>
    <div class="muted">${escapeHTML(mode)}</div>
    ${renderAccountRunWindow(account)}
  `;
}

/**
 * 显示已观察到的额度；渲染过程不触发主动查询。
 * @param {Object} quota 被动额度摘要
 * @return {string} 已转义的 HTML
 */
function renderPassiveQuota(quota) {
  if (quota?.account_error) return `<div class="passive-quota">${escapeHTML(quota.message)}<div>任务侧保留了认证异常记录。点击“额度”重新核验授权并更新状态。</div></div>`;
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

/** 以窗口展示本次真实额度查询。@param {number|string} accountId 账号ID。@param {object} quota 查询回执。@return {void} */
function openQuotaDetail(accountId,quota){
  endRunDetail();const row=state.accounts.find(value=>String(value.id)===String(accountId));
  $('#modal').classList.add('task-quota-modal');$('#modal .modal-titlebar-name').textContent='账号额度';$('#modal-close').setAttribute('aria-label','关闭账号额度');
  const windows=[['five_hour','5 小时'],['seven_day','7 天'],['seven_day_fable','7 天 Fable']];
  $('#modal-content').innerHTML=`<section class="work-quota-content"><div class="work-quota-identity"><span class="initial">${runtimeIcon('users')}</span><div><strong>${escapeHTML(accountDisplayName(row)||`账号 #${accountId}`)}</strong><span>${escapeHTML(`任务账号 #${accountId}`)}</span></div><small>${quota.ok?'查询已更新':'等待有效额度'}</small></div>${!quota.ok?`<p class="work-quota-note" role="status">${escapeHTML(quota.message||'额度接口尚未提供有效窗口')}</p>`:''}<div class="work-quota-windows">${windows.map(([key,label])=>{
    const value=quota[key],raw=value?.used_percentage??value?.utilization,number=Number(raw),known=raw!=null&&raw!==''&&Number.isFinite(number)&&number>=0;
    const date=value?.resets_at?new Date(value.resets_at):null;
    return `<article class="work-quota-window ${key==='seven_day_fable'?'quota-fable':''} ${known&&number>=80?'warning':''}"><header><span>${runtimeIcon('clock')}${label}窗口</span><small>已使用</small></header><div class="work-quota-number">${known?Number(number.toFixed(1)):'—'}${known?'<span>%</span>':''}</div><div class="work-quota-meter" ${known?`role="progressbar" aria-label="${label}已用额度" aria-valuenow="${Math.min(100,number)}" aria-valuemin="0" aria-valuemax="100"`:''}><i style="width:${known?Math.min(100,number):0}%"></i></div><div class="work-quota-remaining"><span>${known?'剩余额度':'额度状态'}</span><strong>${known?Number(Math.max(0,100-number).toFixed(1))+'%':'未观测'}</strong></div><div class="work-quota-reset"><span>重置时间 · 北京时间</span><strong>${date&&Number.isFinite(date.getTime())?escapeHTML(date.toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false})):'暂未提供'}</strong></div></article>`;
  }).join('')}</div><footer class="work-quota-footer"><div>${runtimeIcon('clock')}<span>最近查询 ${escapeHTML(new Date().toLocaleTimeString('zh-CN',{hour12:false}))}<small>通过账号当前线路查询额度</small></span></div><button type="button" class="btn" data-quota-refresh>${runtimeIcon('refresh')}刷新额度</button></footer><p class="work-quota-error" role="alert" hidden></p></section>`;
  const panel=$('.work-quota-content'),button=$('[data-quota-refresh]',panel),generation=state.viewGeneration;
  // 关闭、重开或切区后，旧查询只更新服务端事实，不能重新打开额度弹窗。
  const owns=()=>panel.isConnected&&!$('#modal').classList.contains('hidden')&&$('#modal').classList.contains('task-quota-modal')&&generation===state.viewGeneration;
  button.onclick=async()=>{
    if(button.disabled)return;button.disabled=true;$('.work-quota-error',panel).hidden=true;
    try{const result=await API(`/accounts/${accountId}/quota`,{method:'POST'});if(!owns())return;await renderAccounts();if(owns()){openQuotaDetail(accountId,result);$('[data-quota-refresh]').focus({preventScroll:true});}}
    catch(error){if(owns()){const feedback=$('.work-quota-error',panel);feedback.hidden=false;feedback.textContent='查询失败：'+error.message;}}
    finally{if(owns())button.disabled=false;}
  };
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
/** 展示账号授权配置，关联账号沿用原代理与时区。@param {object|null} account 原任务账号或新建。@return {void} */
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
  const proxyHost=$('#runtime-login-proxy');
  delete proxyHost.dataset.proxyChoice;
  proxyHost.dataset.proxyDisabled=String(bound);
  proxyHost.dataset.proxyLabel=account?.upstream_socks5_host?`${account.upstream_proxy_scheme||'socks5'}://${account.upstream_socks5_host}:${account.upstream_socks5_port||1080}`:'直连';
  proxyHost.hidden=false;$('#acc-use-manual').checked=false;$('#acc-use-manual').disabled=bound;
  $('#acc-proxy-manual').open=!RUNTIME_BASE;
  $('#acc-use-manual').onchange=()=>{proxyHost.hidden=$('#acc-use-manual').checked;};

  $('#acc-force-reauth').value = account ? 'true' : 'false';
  $('.modal-titlebar-name', $('#acc-modal')).firstChild.textContent = account ? '重新授权 ' : '添加任务账号 ';
  $('#acc-modal-stage').textContent = '配置账号与代理';
  openModal('#acc-modal');
}

/** 切换授权配置与终端布局，保留原会话及终端节点。@param {string} which 配置或终端阶段。@return {void} */
function showAccStep(which) {
  $('#acc-modal .modal-card').classList.toggle('login-session',which==='terminal');
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
    return notifyRuntime('启动登录会话失败: ' + e.message);
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
  $('#acc-modal-stage').textContent = '完成授权并提交';

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
  } catch (error) { notifyRuntime('重新登录失败：' + error.message); }
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
        const ready=status.credentials_ready===true;const steps=$$('#acc-modal .upgrade-steps li');steps[1]?.classList.toggle('done',ready);steps[1]?.classList.toggle('active',!ready);steps[2]?.classList.toggle('active',ready);
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
  await window.loadRuntimeTerminal?.();
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
    fontFamily: '"JetBrains Mono Variable", ui-monospace, Menlo, monospace',
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
              inputAllowed = msg.status === 'running' && msg.run_window?.allowed !== false;
              const status = $('#continue-quota-status');
              if (status) status.textContent = msg.run_window?.allowed === false
                ? `${msg.run_window.message}${msg.run_window.next_open_at ? `；下次开放 ${accountLocalTime(msg.run_window.next_open_at, msg.run_window.timezone)}` : ''}`
                : inputAllowed ? '可继续输入' : `${msg.message || '额度等待'}${msg.resume_at ? `；恢复机会 ${formatWarmupTime(msg.resume_at)}` : '；暂无可信恢复时间'}`;
            }
            if (msg.type === 'run_window') {
              inputAllowed = msg.run_window?.allowed !== false;
              const status = $('#continue-quota-status');
              if (status) status.textContent = msg.message;
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
      ? `${al.mode === 'relogin' ? '已重新授权' : '账号已保存'}，仅保存到本地，尚未关联网关账号`
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
      notifyRuntime('提交失败: ' + e.message + '\n\n如果还没登录成功，请先在终端完成 OAuth。');
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
  $('#acc-modal-stage').textContent = '配置账号与代理';
  $('#acc-login-commit').disabled = false;
  if (!skipServerCancel && currentTab() === 'accounts') await renderAccounts();
}

// ===================== Topics =====================
async function renderTopics() {
  if (currentTab() !== 'topics') return;
  const generation = state.viewGeneration;
  if (state.topics.length === 0) {
    try {
      const topics = await API('/topics');
      if (currentTab() !== 'topics' || generation !== state.viewGeneration) return;
      state.topics = topics;
    } catch (e) {
      if (currentTab() === 'topics' && generation === state.viewGeneration) notifyRuntime('加载题库失败: ' + e.message);
      return;
    }
  }

  $('#topics-count').textContent = `(${state.topics.length})`;
  const list = $('#topics-list');
  const filter = state.topicFilter.toLowerCase();

  list.innerHTML = state.topics
    .filter(t => !filter ||
      t.title.toLowerCase().includes(filter) ||
      t.category.toLowerCase().includes(filter) ||
      String(t.no).includes(filter))
    .map(t => `<article class="work-panel work-topic" data-id="${t.id}"><div><span class="work-topic-no">#${String(t.no).padStart(3,'0')}</span><span class="pill">${escapeHTML(t.category||'未分类')}</span></div><h3>${escapeHTML(t.title)}</h3><p>${escapeHTML(t.description)}</p><footer><span>${t.followups?.length||0} 条自动补充</span><button type="button" data-topic-edit="${t.id}">编辑</button><button type="button" data-topic-batch="${t.id}">创建任务 ${runtimeIcon('arrow')}</button></footer></article>`).join('') || '<div class="muted empty-panel">暂无 topic</div>';

  list.onclick = (e) => {
    const card = e.target.closest('.work-topic');
    if (!card) return;
    if(e.target.closest('[data-topic-batch]')){state.pendingTopicId=Number(card.dataset.id);navigateTo('#tasks');return;}
    openTopicModal(Number(card.dataset.id));
  };

  list.onkeydown = event => {if(event.target.closest('button'))return;if(event.key==='Enter' || event.key===' '){const card=event.target.closest('.work-topic');if(card){event.preventDefault();openTopicModal(Number(card.dataset.id));}}};
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
  $('.modal-titlebar-name',$('#topic-modal')).firstChild.textContent=topic?'编辑题目 ':'新建题目 ';
  form.title.value = topic ? topic.title : '';
  form.description.value = topic ? topic.description : '';
  form.followup_1.value = topic?.followups?.[0] || '';
  form.followup_2.value = topic?.followups?.[1] || '';
  form.category.value = topic ? topic.category : '';
  $('#topic-modal-title').textContent = topic ? `#${topic.no}` : '';
  $('#topic-delete').classList.toggle('hidden', !topic);
  openModal('#topic-modal');

  form.onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    const first = String(fd.get('followup_1') || '').trim();
    const second = String(fd.get('followup_2') || '').trim();
    if (second && !first) return notifyRuntime('请先填写第一条补充需求');
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
      notifyRuntime('保存题目失败: ' + err.message);
    } finally {
      submit.disabled = false;
    }
  };

  $('#topic-delete').onclick = async () => {
    if (!topic || !await confirmRuntimeAction(`删除 topic #${topic.no}?`)) return;
    try {
      await API(`/topics/${topic.id}`, { method: 'DELETE' });
      closeModal('#topic-modal');
      state.topics = [];
      await renderTopics();
    } catch (err) {
      notifyRuntime('删除题目失败: ' + err.message);
    }
  };
}

function nextTopicNo() {
  return state.topics.reduce((m, t) => Math.max(m, Number(t.no) || 0), 0) + 1;
}

function openTaskModal(topicNo) {
  if (state.accounts.length === 0) {
    return notifyRuntime('请先添加账号');
  }
  const topic = state.topics.find(t => t.no === topicNo);
  $('#task-modal-title').textContent = `#${topic.no} ${topic.title}`;
  const form = $('#task-form');
  form.topic_no.value = topicNo;
  form.account_id.innerHTML = state.accounts
    .map(a => `<option value="${a.id}">${escapeHTML(accountDisplayName(a))}</option>`).join('');
  const concurrencyLimit = state.accounts[0].cli_concurrency_limit || 2;
  form.elements.concurrency.max = concurrencyLimit;
  form.elements.concurrency.value = Math.min(Number(form.elements.concurrency.value), concurrencyLimit);
  $('.view-head .hint').textContent = `先选账号，再多选 topic；批次随机打乱选中题目，账号最多 ${concurrencyLimit} 并发，按保存的随机间隔投放。Tasks 与项目共用账号容量。`;
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
      navigateTo('#tasks');
    } catch (err) { notifyRuntime('创建任务失败: ' + err.message); }
  };
}

// ===================== Tasks =====================
async function renderTasks() {
  if (currentTab() !== 'tasks') return;
  const generation = state.viewGeneration;
  try {
    const values = await Promise.all([API('/task-batches'), API('/accounts'), API('/topics')]);
    if (currentTab() !== 'tasks' || generation !== state.viewGeneration) return;
    [state.batches, state.accounts, state.topics] = values;
  } catch (e) {
    if (currentTab() === 'tasks' && generation === state.viewGeneration) notifyRuntime('加载任务失败: ' + e.message);
    return;
  }

  const accMap = Object.fromEntries(state.accounts.map(a => [a.id, accountDisplayName(a)]));
  const form = $('#batch-form');
  $('#open-batch-form').onclick=()=>openModal('#batch-create-modal');
  if (state.accounts.length === 0) {
    form.account_id.innerHTML = '';
    $('#batch-topic-list').innerHTML = '<div class="muted">请先添加账号</div>';
    $('#batches-body').innerHTML = '<tr><td colspan="7" class="muted empty-cell">暂无账号，无法启动批次</td></tr>';
    return;
  }
  form.account_id.innerHTML = state.accounts
    .map(a => `<option value="${a.id}">${escapeHTML(accountDisplayName(a))}</option>`).join('');
  paintBatchTopics();
  if(state.pendingTopicId){const selected=$(`#batch-topic-list input[value="${state.pendingTopicId}"]`);if(selected)selected.checked=true;state.pendingTopicId=null;updateBatchSelectedCount();openModal('#batch-create-modal');}

  const body = $('#batches-body');
  $('#work-batch-search').value=state.batchQuery;$('#work-batch-search').oninput=event=>{state.batchQuery=event.target.value;$$('tr',body).forEach(row=>{row.hidden=!!state.batchQuery.trim()&&!row.textContent.toLocaleLowerCase().includes(state.batchQuery.trim().toLocaleLowerCase());});};
  body.innerHTML = state.batches.map(b => `<tr><td><strong>批次 #${b.id}</strong><small>${escapeHTML(accMap[b.account_id]||`账号 #${b.account_id}`)}</small></td><td>${runtimeBadge(b)}${b.status==='quota_wait'?`<small>${escapeHTML(b.quota_policy?.message||b.passive_quota?.message||'等待最新额度')}</small>`:''}</td><td><strong>${b.done_count||0} / ${b.item_count||0}</strong><div class="bar"><i style="width:${b.item_count?Math.min(100,(b.done_count||0)/b.item_count*100):0}%"></i></div></td><td>${b.effective_concurrency??b.concurrency}${b.effective_concurrency!=null&&b.effective_concurrency!==b.concurrency?`<small>已存配置 ${b.concurrency}，受账号上限限制</small>`:''}</td><td>${b.interval_min_sec}–${b.interval_max_sec} 秒</td><td>${renderBatchActions(b)}</td></tr>`).join('')||'<tr><td colspan="6" class="empty-cell">暂无批次</td></tr>';
  $('#work-batch-search').dispatchEvent(new Event('input',{bubbles:true}));

  body.onclick = async (e) => {
    const pauseBatchId = e.target.dataset.pauseBatch;
    if (pauseBatchId && await confirmRuntimeAction(`暂停批次 #${pauseBatchId}? 已运行的 run 会停止，未完成项目可继续。`)) {
      e.target.disabled = true;
      try {
        await API(`/task-batches/${pauseBatchId}/pause`, { method: 'POST' });
        renderTasks();
      } catch (err) {
        notifyRuntime('暂停批次失败: ' + err.message);
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
        notifyRuntime('继续批次失败: ' + err.message);
        e.target.disabled = false;
      }
      return;
    }
    const batchId = e.target.dataset.delBatch;
    if (batchId && await confirmRuntimeAction(`删除批次 #${batchId}?`)) {
      try {
        await API(`/task-batches/${batchId}`, { method: 'DELETE' });
        renderTasks();
      } catch (err) { notifyRuntime('删除批次失败: ' + err.message); }
    }
  };

  $('#batch-topic-search').oninput=event=>{const query=event.target.value.trim().toLocaleLowerCase();$$('#batch-topic-list label').forEach(label=>{label.hidden=!!query&&!label.textContent.toLocaleLowerCase().includes(query);});};
  $('#batch-select-all').onclick = () => {
    $$('#batch-topic-list label:not([hidden]) input[type=checkbox]').forEach(i => { i.checked = true; });
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
    if (topicIds.length === 0) return notifyRuntime('请至少选择一个 topic');
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
      notifyRuntime(`已启动批次 #${res.id}`);
      closeModal('#batch-create-modal');await renderTasks();
    } catch (err) {
      notifyRuntime('启动批次失败: ' + err.message);
    }
  };
}

function paintBatchTopics() {
  const list = $('#batch-topic-list');
  list.innerHTML = state.topics.map(t => `
    <label class="work-pool-item">
      <input type="checkbox" value="${t.id}" />
      <span><strong>#${t.no} ${escapeHTML(t.title)}</strong><small>${escapeHTML(t.category)}</small></span>
    </label>
  `).join('') || '<div class="muted">暂无 topic</div>';
  list.onchange = updateBatchSelectedCount;
  updateBatchSelectedCount();
}

function updateBatchSelectedCount() {
  const n = $$('#batch-topic-list input[type=checkbox]:checked').length;
  const el = $('#batch-selected-count');
  if (el) el.textContent = `已选 ${n} 项`;
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
  $('#modal .modal-titlebar-name').textContent='运行详情';
  $('#modal').classList.add('approved-run-modal');
  $('#modal .modal-titlebar-name').textContent = '运行详情';
  $('#modal-close').setAttribute('aria-label', '关闭运行详情');
  $('#modal-content').innerHTML = `
    <div class="work-run-detail">
      <div class="run-detail-meta"><div><span id="run-detail-status" class="pill pill-queued">等待读取</span><span id="run-detail-kind">运行记录</span><span id="run-detail-account"></span></div><code>${escapeHTML(rid)}</code></div>
      <div class="run-detail-tabs" role="tablist" aria-label="运行详情">
        ${[['overview','概览'],['logs','日志'],['files','产物文件'],['capture','抓包']].map(([key,label],index)=>`<button type="button" role="tab" id="run-tab-${key}" aria-controls="run-panel-${key}" aria-selected="${index === 0}" tabindex="${index ? -1 : 0}" data-run-tab="${key}" class="${index ? '' : 'active'}">${label}${key === 'files' ? '<small id="run-detail-file-count">0</small>' : ''}</button>`).join('')}
      </div>
      <div class="run-detail-scroll">
        <section id="run-panel-overview" role="tabpanel" aria-labelledby="run-tab-overview">
          <div class="run-stat-grid">
            <article><span>输入 Token</span><strong data-stat-key="tokens_in">等待采集</strong><small>本次运行累计输入</small></article>
            <article><span>输出 Token</span><strong data-stat-key="tokens_out">等待采集</strong><small>本次运行累计输出</small></article>
            <article><span>请求数</span><strong data-stat-key="requests">等待采集</strong><small>本次运行累计请求</small></article>
            <article><span>退出码</span><strong data-stat-key="exit_code">待结束</strong><small>进程最终退出状态</small></article>
          </div>
          <div class="hint inline hidden" id="run-detail-stats-error"></div>
          <div class="run-state-notice failure hidden" id="run-detail-error-section"><strong id="run-detail-error-title">错误</strong><pre id="run-detail-error"></pre></div>
          <div class="run-overview-grid">
            <article class="run-info-panel"><header><h3>需求与自动补充</h3><span>本次运行记录</span></header><div class="run-prompt" id="run-detail-followups">等待运行计划</div></article>
            <aside class="run-info-panel"><header><h3>执行配置</h3></header><dl class="run-config-list"><div><dt>运行版本</dt><dd data-stat-key="claude_code_version">未采集</dd></div><div><dt>冻结模型</dt><dd data-stat-key="model_override">未采集</dd></div><div><dt>思考预算</dt><dd data-stat-key="claude_effort_level">未采集</dd></div></dl><p class="run-config-note">配置以本次运行保存的记录为准。</p></aside>
          </div>
        </section>
        <section id="run-panel-logs" role="tabpanel" aria-labelledby="run-tab-logs" hidden><div class="run-log-panel"><header><strong>运行日志</strong><span id="run-detail-log-state">等待日志</span></header><pre class="transcript-pre" id="run-detail-transcript">等待日志</pre><footer>输出按当前运行持续更新</footer></div></section>
        <section id="run-panel-files" role="tabpanel" aria-labelledby="run-tab-files" hidden><div class="run-info-panel"><header><h3>产物文件</h3><span>当前工作目录</span></header><div class="file-tree" id="run-detail-files"><div class="muted">等待文件列表</div></div></div></section>
        <section id="run-panel-capture" role="tabpanel" aria-labelledby="run-tab-capture" hidden><div class="run-empty-state" id="run-detail-capture-empty"><strong>本次运行未启用抓包</strong><p>抓包运行的请求索引和 TLS 观测会显示在这里。</p></div><div class="detail-section hidden" id="run-detail-capture-section"><div class="capture-summary" id="run-detail-capture">等待抓包索引</div></div></section>
      </div><footer class="run-detail-footer"><span>运行记录与实际观测</span><span id="run-detail-updated">正在读取…</span></footer>
    </div>`;
  const modal = $('#modal');
  modal.setAttribute('role', 'dialog'); modal.setAttribute('aria-modal', 'true');
  modal.setAttribute('aria-label', '运行详情');
  modal.onkeydown = event => {
    if (event.key !== 'Tab') return;
    const nodes = [...modal.querySelectorAll('button:not(:disabled),a[href],input,textarea,summary,[tabindex="0"]')].filter(node => node.offsetParent !== null);
    const first = nodes[0], last = nodes[nodes.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
  };
  const tabs = $('#modal-content .run-detail-tabs');
  /** 页签切换保留正文DOM、文件内容和正在进行的观测。@param {HTMLElement} button 目标页签。@return {void} */
  const selectTab = button => {
    for (const tab of tabs.querySelectorAll('[data-run-tab]')) {
      const selected = tab === button;
      tab.classList.toggle('active', selected); tab.setAttribute('aria-selected', String(selected)); tab.tabIndex = selected ? 0 : -1;
      $('#' + tab.getAttribute('aria-controls')).hidden = !selected;
    }
  };
  tabs.onclick = event => { const button = event.target.closest('[data-run-tab]'); if (button) selectTab(button); };
  tabs.onkeydown = event => {
    const buttons = [...tabs.querySelectorAll('[data-run-tab]')], index = buttons.indexOf(event.target);
    if (index < 0 || !['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
    event.preventDefault(); event.stopPropagation();
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + buttons.length) % buttons.length;
    selectTab(buttons[next]); buttons[next].focus();
  };
}

function setRunDetailText(selector, html) {
  const el = $(selector);
  if (el && el.innerHTML !== html) el.innerHTML = html;
}

/** 渲染有界 TLS 白名单摘要。@param {object} tls 公开握手摘要。@return {string} 转义后的 HTML。 */
function renderCaptureTls(tls) {
  const records = Array.isArray(tls?.entries) ? tls.entries : [];
  const rows = records.slice(-8).map(record => {
    const context = record.capture_context || {};
    const fingerprint = record.ja3 || {};
    const fields = {
      direction: record.direction, client_connection_id: record.client_connection_id,
      capture_context: context, capture_context_status: record.capture_context_status,
      parse_status: record.parse_status, target_status: record.target_status,
      legacy_version: record.legacy_version, supported_versions: record.supported_versions,
      cipher_suites: record.cipher_suites,
      extensions: Array.isArray(record.extensions) ? record.extensions.map(item => ({type: item.type, length: item.length})) : null,
      signature_algorithms: record.signature_algorithms, supported_groups: record.supported_groups,
      ec_point_formats: record.ec_point_formats,
      key_share: Array.isArray(record.key_share) ? record.key_share.map(item => ({group: item.group, key_exchange_length: item.key_exchange_length})) : null,
      sni: record.sni, alpn_protocols: Array.isArray(record.alpn_protocols) ? record.alpn_protocols.map(item => item.text ?? '非文本协议') : null,
      ja3: {string: fingerprint.string, md5: fingerprint.md5}, fields_incomplete: record.fields_incomplete,
    };
    return `<details>
      <summary>${escapeHTML(context.claude_code_version || '版本未知')} · JA3 <code>${escapeHTML(fingerprint.md5 || '未生成')}</code> · ${escapeHTML(record.client_connection_id || '连接未知')}</summary>
      <pre class="transcript-pre">${escapeHTML(JSON.stringify(fields, null, 2))}</pre>
    </details>`;
  }).join('');
  const count = tls?.count_exact ? `共 ${tls.total_records ?? records.length} 条握手` : `已扫描 ${tls?.scanned_records ?? records.length} 条有效握手，数量非全量`;
  return `<h4>TLS ClientHello</h4>
    <p class="hint" role="status">${escapeHTML(tls?.message || '该抓包尚未保存 ClientHello 记录')} ${tls?.available ? escapeHTML(count) : ''}</p>
    ${rows || '<div class="muted">暂无可展示的握手</div>'}`;
}

/** 渲染三个入口共用的抓包索引和状态。@param {object} capture 公开抓包摘要。@return {string} 已脱敏 HTML。 */
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
        <td><code>${escapeHTML(e.client_connection_id || '-')}</code></td>
        <td>${escapeHTML(path)}</td>
        <td>${escapeHTML(resp.status ?? '-')} ${escapeHTML({pending: '响应中', interrupted: '中断', complete: '完成'}[e.capture_state] || '')}</td>
        <td>${escapeHTML(req.body_bytes ?? 0)} / ${escapeHTML(resp.body_bytes ?? 0)}</td>
        <td>${escapeHTML(ana.cc_version || '-')}</td>
      </tr>
    `;
  }).join('');
  const fileRows = files.map(f => `
    <div class="file">${escapeHTML(f.path)}<span class="size">${formatSize(f.size || 0)}</span></div>
  `).join('') || '<div class="muted">暂无抓包文件</div>';
  const tlsHTML = renderCaptureTls(capture.tls_clienthello);
  const captureStats = `
    <p class="hint" role="status">${escapeHTML(capture.message || '仅展示已落盘数据')}</p>
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
      <div class="muted">${escapeHTML(capture.message || '尚未采到目标流量')}</div>
      <div class="file-tree capture-files">${fileRows}</div>
      ${tlsHTML}
    `;
  }
  return `
    ${captureStats}
    <div class="hint inline">完整请求体和响应体保存在 flows 目录；此处只展示脱敏索引。</div>
    <div class="file-tree capture-files">${fileRows}</div>
    ${tlsHTML}
    <table class="data capture-table">
      <thead><tr><th>flow</th><th>客户端连接</th><th>请求</th><th>状态</th><th>请求/响应字节</th><th>cc_version</th></tr></thead>
      <tbody>${entryRows || '<tr><td colspan="6" class="muted empty-cell">暂无目标请求</td></tr>'}</tbody>
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
  const task = state.tasks.find(item => item.id === run.task_id);
  const account = state.accounts.find(item => item.id === run.account_id);
  $('#modal .modal-titlebar-name').textContent = task?.title || '运行详情';
  setRunDetailText('#run-detail-account', escapeHTML(accountDisplayName(account) || '账号信息未提供'));
  setRunDetailText('#run-detail-kind', escapeHTML(({normal:'普通任务',capture:'抓包任务',warmup:'养号任务'})[run.run_kind] || '运行记录'));
  setRunDetailText('#run-detail-updated', '更新于 ' + escapeHTML(new Date().toLocaleTimeString('zh-CN', {hour12:false})));
  setRunDetailText('#run-detail-log-state', isLiveRunStatus(run.status) ? '持续观测中' : '本次运行已结束');

  setRunDetailText('#run-detail-followups', renderRunFollowups(run));

  const statusEl = $('#run-detail-status');
  if (statusEl) {
    const nextClass = `pill pill-${safeStatus}`;
    if (statusEl.className !== nextClass) statusEl.className = nextClass;
    const label = runStatusLabel(run);
    if (statusEl.textContent !== label) statusEl.textContent = label;
  }

  setRunDetailText('[data-stat-key="tokens_in"]', renderStatValue(stats, 'tokens_in'));
  setRunDetailText('[data-stat-key="tokens_out"]', renderStatValue(stats, 'tokens_out'));
  setRunDetailText('[data-stat-key="requests"]', renderStatValue(stats, 'requests'));
  setRunDetailText('[data-stat-key="exit_code"]', escapeHTML(run.exit_code ?? (isLiveRunStatus(run.status) ? '待结束' : '未采集')));
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
    $('#run-detail-capture-empty').classList.toggle('hidden', isCapture);
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
  $$('[data-run-status]').forEach(button=>button.classList.toggle('active',button.dataset.runStatus===state.runStatus));
  $('#work-run-search').value=state.runQuery;$('#work-run-search').oninput=event=>{state.runQuery=event.target.value;paintRuns(state.runs);};
  $('#work-run-status').onclick=event=>{const button=event.target.closest('[data-run-status]');if(!button)return;state.runStatus=button.dataset.runStatus;$$('[data-run-status]').forEach(item=>item.classList.toggle('active',item===button));paintRuns(state.runs);};
  $('#work-capture-new').onclick=()=>openModal('#runtime-capture-modal');
  $('#runtime-open-settings').onclick=()=>{paintClaudeCodeVersionSetting();paintRuntimeModelSetting();paintRuntimeEffortSetting();$$('.runtime-setting-provenance').forEach(node=>{node.open=false;});$('#runtime-settings-feedback').textContent='配置影响后续新执行；额度等待恢复沿用原参数。';openModal('#runtime-settings-modal');};
  $('#runtime-settings-save').onclick=saveRuntimeSettings;
  if (currentTab() !== 'runs') return;
  const generation = state.viewGeneration;
  const current = () => currentTab() === 'runs' && generation === state.viewGeneration;
  try {
    const values = await Promise.all([API('/accounts'), API('/tasks'), API('/topics'),
      API('/settings/runtime-model'), API('/settings/runtime-effort'), API('/settings/claude-code-version')]);
    if (!current()) return;
    [state.accounts, state.tasks, state.topics, state.runtimeModel, state.runtimeEffort, state.claudeCodeVersion] = values;
  } catch (e) {
    if (current()) notifyRuntime('加载运行依赖失败: ' + e.message);
    return;
  }
  bindRuntimeModelForm();
  bindRuntimeEffortForm();
  bindClaudeCodeVersionForm();
  bindCaptureForm();
  $('#runtime-settings-save').disabled=false;
  paintRuns(state.runs);
  if (state.runsEventSource) state.runsEventSource.close();
  state.runsEventSource = new EventSource(RUNTIME_BASE + '/api/runs-stream');
  state.runsEventSource.addEventListener('runs', (e) => {
    if (!current()) return;
    try {
      state.runs = JSON.parse(e.data);
      paintRuns(state.runs);
    } catch {}
  });
  // 首次也拉一下
  API('/runs').then(rs => { if (current()) { state.runs = rs; paintRuns(rs); } }).catch(() => {});
}

/** 保存有修改的后续运行配置，分别回读原接口并明确部分失败。@return {Promise<void>} 保存完成。 */
async function saveRuntimeSettings(){
  if(state.runtimeSettingsSaving?.generation===state.viewGeneration)return;
  const fields=[['claude-code-version-form','claude_code_version'],['runtime-model-form','default_model'],['runtime-effort-form','effort_level']];
  const changed=fields.map(([id,name])=>({form:$('#'+id),name})).filter(({form,name})=>form.elements[name].value!==form.dataset.savedValue);
  if(changed.some(({form})=>!form.reportValidity()))return;
  const request={generation:state.viewGeneration};state.runtimeSettingsSaving=request;
  const modal=$('#runtime-settings-modal'),button=$('#runtime-settings-save');button.disabled=true;$$('[data-close]',modal).forEach(node=>{node.disabled=true;});
  try{
    const results=await Promise.all(changed.map(({form})=>form.onsubmit(new Event('submit',{cancelable:true}))));
    if(state.runtimeSettingsSaving!==request||request.generation!==state.viewGeneration)return;
    if(results.every(Boolean)){state.runtimeSettingsSaving=null;closeModal('#runtime-settings-modal');notifyRuntime('后续运行配置已保存');}
    else $('#runtime-settings-feedback').textContent='部分配置保存失败。已保存的配置保留，请检查失败项后重试。';
  }finally{
    if(state.runtimeSettingsSaving===request)state.runtimeSettingsSaving=null;
    button.disabled=false;$$('[data-close]',modal).forEach(node=>{node.disabled=false;});
  }
}

function paintRuntimeModelSetting() {
  const form = $('#runtime-model-form');
  if (!form || !state.runtimeModel) return;
  const configured = state.runtimeModel.configured_model;
  const effective = state.runtimeModel.effective_model || state.runtimeModel.env_default_model || '-';
  form.default_model.value = configured || '';
  form.dataset.savedValue=form.default_model.value;
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
    if(btn.disabled)return false;const generation=state.viewGeneration;
    btn.disabled = true;
    if (resetBtn) resetBtn.disabled = true;
    try {
      state.runtimeModel = await API('/settings/runtime-model', {
        method: 'PUT',
        body: JSON.stringify(body),
      });
      if(generation===state.viewGeneration)paintRuntimeModelSetting();
      return true;
    } catch (err) {
      notifyRuntime('保存默认模型失败: ' + err.message);return false;
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
  form.dataset.savedValue=form.effort_level.value;
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
    if(btn.disabled)return false;const generation=state.viewGeneration;
    btn.disabled = true;
    if (resetBtn) resetBtn.disabled = true;
    try {
      state.runtimeEffort = await API('/settings/runtime-effort', {
        method: 'PUT',
        body: JSON.stringify(body),
      });
      if(generation===state.viewGeneration)paintRuntimeEffortSetting();
      return true;
    } catch (err) {
      notifyRuntime('保存思考预算失败: ' + err.message);return false;
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
  form.dataset.savedValue=form.claude_code_version.value;
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
    if(btn.disabled)return false;const generation=state.viewGeneration;
    btn.disabled = true;
    if (resetBtn) resetBtn.disabled = true;
    try {
      state.claudeCodeVersion = await API('/settings/claude-code-version', {
        method: 'PUT',
        body: JSON.stringify(body),
      });
      if(generation===state.viewGeneration)paintClaudeCodeVersionSetting();
      return true;
    } catch (err) {
      notifyRuntime('保存 Claude Code 版本失败: ' + err.message);return false;
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
    .map(a => `<option value="${a.id}">${escapeHTML(accountDisplayName(a))}</option>`).join('');
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
    if (state.accounts.length === 0) return notifyRuntime('请先添加账号');
    if (state.topics.length === 0) return notifyRuntime('请先添加题目');
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
      claude_code_version: (fd.get('claude_code_version') || '').trim() || null,
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
      form.claude_code_version.value = '';
      form.effort_level.value = '';
      form.permission_mode.value = 'bypassPermissions';
      await Promise.all([
        API('/tasks').then(ts => { state.tasks = ts; }),
        API('/runs').then(rs => { state.runs = rs; }),
      ]).catch(() => {});
      paintRuns(state.runs);
      closeModal('#runtime-capture-modal');
      openRunDetail(res.run_id);
    } catch (err) {
      notifyRuntime('启动抓包失败: ' + err.message);
    } finally {
      btn.disabled = false;
    }
  };
}

function paintRuns(runs) {
  const body = $('#runs-body');
  if (!body) return;
  const accMap = Object.fromEntries(state.accounts.map(a => [a.id, accountDisplayName(a)]));
  const taskMap = Object.fromEntries(state.tasks.map(t => [t.id, t]));
  const filtered=runs.filter(row=>(state.runStatus==='all'||(state.runStatus==='running'?['running','queued','stopping','quota_wait']:['failed','timeout','auth_failed']).includes(row.status))&&[row.id,accMap[row.account_id],taskMap[row.task_id]?.title].join(' ').toLocaleLowerCase().includes(state.runQuery.trim().toLocaleLowerCase()));
  patchRuntimeContent(body, filtered.map(r => {
    const task = taskMap[r.task_id];
    const runKind = r.run_kind || 'normal';
    const tname = task ? `${['project_iteration', 'project_review'].includes(runKind) ? '' : `#${task.topic_no} `}${escapeHTML(task.title)}` : `task#${r.task_id}`;
    const kind = runKind === 'capture'
      ? ' <span class="pill pill-capture">抓包</span>'
      : (runKind === 'warmup' ? ' <span class="pill pill-warmup">养号</span>' : runKind === 'project_review' ? ' <span class="pill">同模型独立评审</span>' : runKind === 'project_iteration' ? ' <span class="pill">项目任务</span>' : '');
    const dur = r.read_only && !r.ended_at ? '历史记录' : r.status === 'quota_wait' ? (r.quota_resume_at ? `恢复 ${formatWarmupTime(r.quota_resume_at)}` : '等待可信恢复时间') : (r.started_at && r.ended_at) ? `${(r.ended_at - r.started_at).toFixed(0)}s` :
                (r.started_at ? `${(Date.now()/1000 - r.started_at).toFixed(0)}s` : '-');
    const terminal = ['success', 'failed', 'timeout', 'stopped', 'auth_failed'].includes(r.status);
    return `
      <tr data-runtime-key="${escapeHTML(r.id)}">
        <td><button type="button" class="work-title-button" data-detail="${escapeHTML(r.id)}">${tname}</button><small><code>${escapeHTML(r.id)}</code>${kind}</small></td>
        <td>${escapeHTML(accMap[r.account_id] || `acc#${r.account_id}`)}</td>
        <td>${runtimeBadge(r)}${r.read_only?'<small>只读历史</small>':''}</td>
        <td>${dur}</td>
        <td>${r.exit_code ?? '-'}</td>
        <td><div class="op-actions run-actions">
          <button class="btn btn-sm" data-detail="${r.id}">详情</button>
          ${!r.read_only && ['queued', 'running', 'quota_wait'].includes(r.status) ? `<button class="btn btn-sm btn-danger" data-stop="${r.id}">停止</button>` : ''}
          ${terminal && !['project_iteration', 'project_review'].includes(runKind) ? `<button class="btn btn-sm btn-primary" data-continue="${r.id}">继续</button>` : ''}
          ${terminal && !r.read_only ? `<button class="btn btn-sm btn-danger" data-del-run="${r.id}">删除</button>` : ''}
        </div></td>
      </tr>
    `;
  }).join('') || '<tr><td colspan="6" class="empty-cell">暂无运行</td></tr>');

  body.onclick = async (e) => {
    const rid = e.target.dataset.detail;
    if (rid) openRunDetail(rid);
    const stopId = e.target.dataset.stop;
    if (stopId && await confirmRuntimeAction(`停止 run ${stopId}?`)) {
      e.target.disabled = true;
      try { await API(`/runs/${stopId}/stop`, { method: 'POST' }); }
      catch (err) { notifyRuntime('停止失败: ' + err.message); e.target.disabled = false; }
      return;
    }
    const contId = e.target.dataset.continue;
    if (contId) {
      e.target.disabled = true;
      try { await startContinueRun(contId); }
      catch (err) { notifyRuntime('继续对话失败: ' + err.message); }
      finally { e.target.disabled = false; }
      return;
    }
    const delId = e.target.dataset.delRun;
    if (delId && await confirmRuntimeAction(`删除 run ${delId}?`)) {
      try { await API(`/runs/${delId}`, { method: 'DELETE' }); }
      catch (err) { notifyRuntime('删除运行失败: ' + err.message); }
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
  $('#modal').classList.remove('approved-run-modal','task-quota-modal');
  $('#modal-content').onclick=null;
  if (detail?.opener?.isConnected) detail.opener.focus({ preventScroll:true });
}

function renderStatValue(stats, key) {
  if (stats?.error) return '<span class="stat-waiting">加载失败</span>';
  if (!stats || stats.available === false) return '<span class="stat-waiting">等待采集</span>';
  if ((key === 'tokens_in' || key === 'tokens_out') && stats.usage_available === false) {
    return '<span class="stat-waiting">等待采集</span>';
  }
  const value = stats[key] ?? 0;
  return escapeHTML(typeof value === 'number' ? value.toLocaleString() : value);
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
    const error = $('#run-detail-stats-error');
    if (error) { error.classList.remove('hidden'); error.textContent = `加载失败：${e.message}，正在重试`; }
    detail.timer = setTimeout(refreshRunDetail, 2500);
  }
}

async function openRunDetail(rid) {
  // 新控制台在顶层渲染复用详情，独立旧地址继续使用本页容器。
  let nativeDetails = false;
  try { nativeDetails = window.parent !== window && !!window.parent.document.querySelector('[data-native-run-details]'); } catch { /* 跨源独立嵌入沿用当前页面。 */ }
  if (nativeDetails) {
    const run = state.runs.find(item => item.id === rid);
    const task = state.tasks.find(item => item.id === run?.task_id);
    const account = state.accounts.find(item => item.id === run?.account_id);
    window.parent.postMessage({type:'runtime:run-detail',id:rid,title:task?.title || '运行详情',accountName:accountDisplayName(account) || ''},location.origin);
    return;
  }
  endRunDetail();
  state.runDetail = {
    rid,
    opener: document.activeElement,
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
  renderRunDetailShell(rid);
  state.runDetail.rendered = true;
  openModal('#modal');
  $('#modal-close').focus();
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
let modalOrder=0;
const modalOpeners=new WeakMap();
/** 按打开顺序维护层级，子窗口关闭后保留父工作区。@param {string} sel 选择器。@return {void} */
function openModal(sel) { const modal=$(sel);if(modal.classList.contains('hidden'))modalOpeners.set(modal,document.activeElement);modal.classList.remove('hidden');modal.dataset.modalOrder=String(++modalOrder);modal.style.zIndex=String(100+modalOrder); }
/**
 * 统一关闭弹窗，时段弹窗的旧请求失效后不得操作下一次打开的表单。
 * @param {string} sel 弹窗选择器
 * @return {void}
 */
function closeModal(sel) {
  if(sel==='#runtime-confirm-modal'&&runtimeConfirmation){const pending=runtimeConfirmation;runtimeConfirmation=null;pending.resolve(false);}
  if (sel === '#environment-workspace') return closeEnvironmentWorkspace();
  if (sel === '#native-kernel-modal') return closeNativeKernelDialog();
  if (sel === '#cpu-resource-modal') return closeCpuResourceDialog();
  if (sel === '#content-capture-modal') return closeContentCaptureDialog();
  if(sel==='#runtime-settings-modal'&&state.runtimeSettingsSaving?.generation===state.viewGeneration)return false;
  if (sel === '#cli-settings-modal') state.cliSettings = null;
  if (sel === '#work-capture-modal') state.workCapture = null;
  if (sel === '#run-window-modal') return closeRunWindowConfig();
  const modal=$(sel);modal?.classList.add('hidden');const opener=modal&&modalOpeners.get(modal);if(opener?.isConnected)opener.focus({preventScroll:true});
}

let runtimeConfirmation=null, runtimeToastTimer;
/** 展示与确认稿一致的异步确认，取消及离页返回false。@param {string} message 操作影响。@return {Promise<boolean>} 明确选择。 */
function confirmRuntimeAction(message) {
  closeModal('#runtime-confirm-modal');
  return new Promise(resolve=>{
    runtimeConfirmation={resolve};$('#runtime-confirm-message').textContent=message;
    $('#runtime-confirm-accept').onclick=()=>{const pending=runtimeConfirmation;runtimeConfirmation=null;closeModal('#runtime-confirm-modal');pending?.resolve(true);};
    openModal('#runtime-confirm-modal');$('#runtime-confirm-modal [data-close]').focus();
  });
}
/** 反馈操作结果，正文以文本呈现。@param {string} message 消息。@return {void} */
function notifyRuntime(message) {
  clearTimeout(runtimeToastTimer);$('#runtime-toast-message').textContent=String(message);$('#runtime-toast').classList.remove('hidden');
  const close=()=>{clearTimeout(runtimeToastTimer);$('#runtime-toast').classList.add('hidden');};$('#runtime-toast-close').onclick=close;runtimeToastTimer=setTimeout(close,6000);
}

/** 关闭工程配置与抓包窗口，使换账号、换空间前的回执失效。@return {void} */
function closeProjectDialogs() {
  closeModal('#projects-research');
  closeModal('#projects-delivery');
  closeModal('#cli-settings-modal');
  closeModal('#work-capture-modal');
}

/**
 * 打开统一账号版本配置，迭代页只编辑本空间的抓包开关。
 * @param {number} accountId 当前账号。
 * @param {string|null} namespace projects、warmup 或账号页的 null。
 * @return {Promise<void>} 配置读取完成。
 */
async function openCliSettingsConfig(accountId, namespace = null) {
  closeModal('#cli-settings-modal');
  const account = state.accounts.find(item => item.id === accountId);
  const request = {accountId, namespace, generation: state.viewGeneration, loaded: false};
  state.cliSettings = request;
  const form = $('#cli-settings-form'), submit = form.querySelector('[type=submit]');
  const current = () => state.cliSettings === request && request.generation === state.viewGeneration;
  const field = namespace === 'warmup' ? 'warmup_capture_enabled' : 'projects_capture_enabled';
  let baselineName = accountDisplayName(account);
  const fill = value => {
    baselineName = value.display_name || accountDisplayName(account);
    form.elements.display_name.value = baselineName;
    form.elements.claude_code_version.value = value.claude_code_version || '';
    form.elements.capture_enabled.checked = value[field] === true;
    $('#cli-settings-title').textContent = namespace ? '执行配置' : `任务账号配置 · ${baselineName}`;
    $('#cli-settings-effective').textContent = `当前有效版本：${value.effective_claude_code_version} · 来源：${value.claude_code_version_source === 'account' ? '账号配置' : '全局配置'}`;
  };
  form.reset(); submit.disabled = true;
  $('#cli-settings-title').textContent = namespace ? '执行配置' : `任务账号配置 · ${baselineName}`;
  $('#cli-settings-name').classList.toggle('hidden', namespace != null);
  $('#cli-settings-account-links').classList.toggle('hidden', namespace != null);
  $('#cli-settings-maintenance').classList.toggle('hidden', namespace != null || !RUNTIME_BASE || account?.cc2api_account_id == null);
  $('#cli-settings-maintenance').open = false;
  $('#cli-settings-capture').classList.toggle('hidden', namespace == null);
  $('#cli-settings-capture-hint').classList.toggle('hidden', namespace == null);
  $('#cli-settings-effective').classList.toggle('hidden', namespace == null);
  $('#cli-settings-effective').textContent = '';
  $('#cli-settings-feedback').textContent = '正在读取配置…';
  $('#cli-settings-feedback').classList.remove('is-error');
  submit.textContent = namespace ? '保存执行配置' : '保存账号配置';
  form.elements.display_name.disabled = true;
  form.elements.claude_code_version.disabled = true;
  form.elements.capture_enabled.disabled = true;
  $('#cli-settings-gateway').disabled = account?.cc2api_account_id == null;
  $('#cli-settings-environment').disabled = !RUNTIME_BASE;
  $('#cli-settings-gateway').onclick = () => { closeModal('#cli-settings-modal');openAccountProxyConfig(accountId); };
  $('#cli-settings-environment').onclick = () => { closeModal('#cli-settings-modal');openRunWindowConfig(accountId); };
  $('#cli-settings-quota').onclick = () => { if (account) openWarmupModal(account); };
  $('#cli-settings-process').dataset.cc2Process = String(accountId);
  $('#cli-settings-process').onclick = event => $('#accounts-body').onclick(event);
  openModal('#cli-settings-modal');
  form.onsubmit = async event => {
    event.preventDefault();
    if (!current() || !request.loaded || submit.disabled) return;
    const payload = {claude_code_version: form.elements.claude_code_version.value.trim() || null};
    if (namespace != null) payload[field] = form.elements.capture_enabled.checked;
    else if (form.elements.display_name.value.trim() !== baselineName) payload.display_name = form.elements.display_name.value.trim();
    submit.disabled = true;
    $('#cli-settings-feedback').classList.remove('is-error');
    try {
      const saved = await API(`/accounts/${accountId}/cli-settings`, {method: 'PUT', body: JSON.stringify(payload)});
      if (!current()) return;
      fill(saved);
      if (namespace == null) {
        closeModal('#cli-settings-modal');
        await renderAccounts();
        if (request.generation === state.viewGeneration) notifyRuntime('账号配置已保存');
      } else $('#cli-settings-feedback').textContent = '配置已保存，后续新执行生效。';
    } catch (error) {
      if (current()) {
        $('#cli-settings-feedback').classList.add('is-error');
        $('#cli-settings-feedback').textContent = `保存失败：${error.message}`;
      }
    } finally { if (current()) submit.disabled = false; }
  };
  try {
    const value = await API(`/accounts/${accountId}/cli-settings`);
    if (!current()) return;
    fill(value); request.loaded = true;
    form.elements.display_name.disabled = namespace != null;
    form.elements.claude_code_version.disabled = false;
    form.elements.capture_enabled.disabled = namespace == null;
    submit.disabled = false;
    $('#cli-settings-feedback').textContent = '';
  } catch (error) {
    if (current()) {
      $('#cli-settings-feedback').classList.add('is-error');
      $('#cli-settings-feedback').textContent = `读取失败：${error.message}`;
    }
  }
}

/**
 * 查看当前或历史工作的抓包；手动刷新只读取已落盘内容。
 * @param {string} workId 已登记的工作标识。
 * @param {string} namespace 项目或养号空间。
 * @return {Promise<void>} 首次详情读取完成。
 */
async function openWorkCapture(workId, namespace) {
  closeModal('#work-capture-modal');
  const request = {workId, namespace, revision: 0};
  state.workCapture = request;
  const prefix = namespace === 'warmup' ? '/accounts/warmup/pi' : '/projects';
  const button = $('#work-capture-refresh');
  const refresh = async () => {
    const revision = ++request.revision;
    button.disabled = true;
    try {
      const capture = await API(`${prefix}/work/${encodeURIComponent(workId)}/capture`);
      if (state.workCapture === request && revision === request.revision){
        const host=$('#work-capture-view');$('#work-capture-status').textContent='';
        if(RUNTIME_BASE&&window.parent!==window){host.dataset.captureUrl=RUNTIME_BASE+'/api'+prefix+'/work/'+encodeURIComponent(workId)+'/capture/file';host.dataset.capturePayload=JSON.stringify(capture);}
        else host.innerHTML=renderCaptureDetail(capture);
      }
    } catch (error) {
      if (state.workCapture === request && revision === request.revision)
        $('#work-capture-status').textContent = `读取抓包失败：${error.message}`;
    } finally { if (state.workCapture === request && revision === request.revision) button.disabled = false; }
  };
  delete $('#work-capture-view').dataset.capturePayload;
  $('#work-capture-status').textContent = '正在读取抓包…';
  button.onclick = refresh;
  openModal('#work-capture-modal');
  await refresh();
}

document.addEventListener('click', (e) => {
  const closeButton = e.target.closest('#modal-close,[data-close]');
  if (closeButton && !closeButton.disabled) {
    const sel = closeButton.dataset.close || '#modal';
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
    tickAccountRunWindows();
  };
  tick();
  setInterval(tick, 1000);
}

function bindShortcuts() {
  const TAB_KEYS = { '1': 'accounts', '2': 'environments', '3': 'topics', '4': 'tasks', '5': 'runs', '6': 'projects' };
  document.addEventListener('keydown', (e) => {
    if(e.defaultPrevented)return;
    const inField = /^(INPUT|TEXTAREA|SELECT)$/i.test(e.target.tagName);
    const topModal=$$('.modal:not(.hidden)').filter(node=>node.getClientRects().length).sort((a,b)=>Number(a.dataset.modalOrder||0)-Number(b.dataset.modalOrder||0)).at(-1);
    // 弹窗键盘操作只在当前层内循环，避免跳到背景页或父文档侧栏。
    if(e.key==='Tab'&&topModal&&!e.defaultPrevented){
      const nodes=$$('button:not(:disabled),a[href],input:not(:disabled):not([type=hidden]),select:not(:disabled),textarea:not(:disabled),summary,[tabindex="0"]',topModal).filter(node=>node.getClientRects().length&&node.tabIndex>=0);
      const index=nodes.indexOf(document.activeElement);
      if(nodes.length&&(e.shiftKey&&index<=0||!e.shiftKey&&index===nodes.length-1)){e.preventDefault();nodes[e.shiftKey?nodes.length-1:0].focus();}
      return;
    }


    // Esc: close any open modal —— 但 data-no-esc 的模态框(如登录框)免疫
    if (e.key === 'Escape') {
      $$('.modal:not(.hidden)').sort((a,b)=>Number(a.dataset.modalOrder||0)-Number(b.dataset.modalOrder||0)).slice(-1).forEach((m) => {
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

    if(topModal)return;
    if (inField) return;     // 后续快捷键在输入框中不响应

    // 登录框未关之前，数字键和搜索键都不导航，防止键盘漏到底层页面。
    if ($('#auth-modal') && !$('#auth-modal').classList.contains('hidden')) return;

    // 项目页优先搜索当前项目池，其它页面沿用题库搜索。
    if (e.key === '/') {
      e.preventDefault();
      if (currentTab() === 'environments') { $('#environment-search')?.focus(); return; }
      if (['projects', 'warmup'].includes(currentTab())) {
        const filter = $('#projects-filter');
        const settings = filter?.closest('details');
        if (settings) settings.open = true;
        filter?.focus();
        return;
      }
      if (currentTab() !== 'topics') navigateTo('#topics');
      setTimeout(() => { const f = $('#topic-filter'); if (f) f.focus(); }, 60);
      return;
    }

    // 数字快捷键与导航栏顺序保持一致。
    if (TAB_KEYS[e.key]) {
      e.preventDefault();
      navigateTo('#' + TAB_KEYS[e.key]);
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
      if (!await confirmRuntimeAction('退出登录?')) return;
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
  else if (window.parent !== window) window.parent.postMessage({type:'runtime:ready'},location.origin);
}) ();
