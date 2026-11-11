/** 账号环境视图；与主后台共享视觉，操作沿用既有管理合同。 */
const ENVIRONMENT_STATES = {ready: '就绪', stopped: '已停止', starting: '启动中',
  reconcile: '待对账', cli_reconcile: 'CLI 待对账', profile_reauth: '画像授权中',
  profile_reauth_reconcile: '画像待对账'};
const KERNEL_STATES = {idle: '可准备', preparing: '正在下载并校验', draining: '等待在途请求结束',
  switching: '预热候选', restoring: '恢复原版', finishing: '核对并开放接单', active: '已生效',
  failed: '保持原版', restored: '已恢复原版', reconcile: '待对账'};
const KERNEL_BUSY_STATES = ['preparing', 'draining', 'switching', 'restoring', 'finishing'];

/** 使旧列表回执和本页轮询失效，后台已提交操作继续由原所有者收口。@return {void} */
function leaveEnvironments() {
  const ui = state.environmentUI;
  ui.request += 1;
  clearTimeout(ui.timer);
  ui.timer = null;
  closeNativeKernelDialog(true);
}

/**
 * 读取当前环境快照，结果按页面代次和请求顺序归属。
 * @return {Promise<void>} 读取及当前页面更新完成。
 */
async function renderEnvironments() {
  if (currentTab() !== 'environments') return;
  const ui = state.environmentUI, generation = state.viewGeneration, request = ++ui.request;
  clearTimeout(ui.timer);
  ui.timer = null;
  const current = () => currentTab() === 'environments' && generation === state.viewGeneration && request === ui.request;
  const refresh = $('#environment-refresh');
  if (!refresh) return;
  refresh.disabled = true;
  const search = $('#environment-search'), filter = $('#environment-status');
  if (search.value !== ui.query) search.value = ui.query;
  search.oninput = () => { ui.query = search.value; paintEnvironments(); };
  filter.onchange = () => { ui.status = filter.value; paintEnvironments(); };
  refresh.onclick = renderEnvironments;
  $('#environment-list').onclick = event => {
    const button = event.target.closest('button');
    if (button && !button.disabled) handleEnvironmentAction(button);
  };
  try {
    const rows = await API('/environments');
    if (!current()) return;
    ui.rows = rows;
    ui.loaded = true;
    $('#environment-feedback').textContent = '';
    paintEnvironments();
  } catch (error) {
    if (!current()) return;
    $('#environment-feedback').textContent = '读取环境失败：' + error.message + (ui.loaded ? '。当前展示上次读取结果。' : '。请点击刷新重试。');
    if (!ui.loaded) $('#environment-list').innerHTML = '<p class="env-empty">环境数据读取失败，请刷新重试。</p>';
  } finally {
    if (current()) {
      refresh.disabled = false;
      // 操作期间只串行读取状态；离页立即释放定时器，避免迟到回执污染下一页。
      if (ui.pending.size || ui.rows.some(row => KERNEL_BUSY_STATES.includes(row.native_kernel?.state))) {
        ui.timer = setTimeout(renderEnvironments, 2000);
      } else if (ui.rows.some(row => row.native_preparation)) {
        ui.timer = setTimeout(renderEnvironments, 20000);
      }
    }
  }
}

/**
 * 重绘环境卡片，工具栏和弹窗位于重绘区外，保护用户输入。
 * @return {void}
 */
function paintEnvironments() {
  if (currentTab() !== 'environments') return;
  const ui = state.environmentUI, list = $('#environment-list');
  if (!list) return;
  const focus = list.contains(document.activeElement) ? document.activeElement.dataset.envFocus : null;
  const counts = [ui.rows.length, ui.rows.filter(row => row.state === 'ready').length,
    ui.rows.filter(row => row.state === 'stopped').length, ui.rows.filter(row => row.native_kernel).length];
  $('#environment-summary').innerHTML = ['全部环境', '就绪', '已停止', '内核试点'].map((label, index) =>
    `<div class="env-metric"><span>${label}</span><strong>${counts[index]}</strong></div>`).join('');
  const statuses = new Set(ui.rows.map(row => row.state || 'unknown'));
  if (ui.status !== 'all') statuses.add(ui.status);
  const select = $('#environment-status');
  const options = '<option value="all">全部状态</option>' + [...statuses].sort().map(value =>
    `<option value="${escapeHTML(value)}" ${ui.status === value ? 'selected' : ''}>${escapeHTML(ENVIRONMENT_STATES[value] || `未知状态：${value}`)}</option>`).join('');
  if (document.activeElement !== select && select.innerHTML !== options) select.innerHTML = options;
  select.value = ui.status;
  const query = ui.query.trim().toLocaleLowerCase();
  const rows = ui.rows.filter(row => (ui.status === 'all' || (row.state || 'unknown') === ui.status)
    && `${row.name || ''} ${row.environment_id || ''}`.toLocaleLowerCase().includes(query));
  $('#environment-result-count').textContent = `显示 ${rows.length} / ${ui.rows.length} 个环境`;
  list.innerHTML = rows.map(renderEnvironmentCard).join('') || `<p class="env-empty">${ui.rows.length ? '没有匹配的环境，请调整搜索或筛选。' : '暂无账号环境。'}</p>`;
  $$('details[data-env-details]', list).forEach(details => {
    details.open = ui.expanded.has(details.dataset.envDetails);
    details.ontoggle = () => {
      if (!details.isConnected) return;
      if (details.open) ui.expanded.add(details.dataset.envDetails);
      else ui.expanded.delete(details.dataset.envDetails);
    };
  });
  if (focus) $$('[data-env-focus]', list).find(node => node.dataset.envFocus === focus)?.focus({preventScroll: true});
}

/**
 * 按实际环境字段展示摘要及独立维护入口。
 * @param {object} row 服务器公开环境摘要。
 * @return {string} 已转义的账号卡片。
 */
function renderEnvironmentCard(row) {
  const id = row.environment_id, fingerprint = row.fingerprint || {}, ui = state.environmentUI;
  const status = ENVIRONMENT_STATES[row.state] || `未知状态：${row.state || '未提供'}`;
  const tone = row.state === 'ready' ? 'good' : row.state === 'stopped' ? 'muted' : 'warning';
  const pending = ui.pending.has(id);
  const roleLabels = {running: '运行中', exited: '已退出', stopped: '已停止', created: '已创建', restarting: '重启中', missing: '缺失'};
  const roles = [['cli', 'CLI'], ['network', '网络'], ['sender', 'API']].map(([key, label]) => {
    const value = row.role_status?.[key];
    return `<span class="env-role ${value === 'running' ? 'env-good' : 'env-muted'}"><i aria-hidden="true"></i>${label} ${escapeHTML(roleLabels[value] || '待核对')}</span>`;
  }).join('');
  const ownership = row.credential_ownership;
  const action = (operation, label, disabled = false) => `<button type="button" class="btn btn-sm ${['stop', 'rebuild'].includes(operation) ? 'btn-danger' : ''}" data-operation="${operation}" data-environment="${escapeHTML(id)}" data-env-focus="${escapeHTML(id + ':' + operation)}" ${disabled || pending ? 'disabled' : ''}>${label}</button>`;
  return `<article class="env-card" aria-label="${escapeHTML(row.name || '未命名环境')}">
    <header class="env-card-head"><div><h3>${escapeHTML(row.name || '未命名环境')}</h3><p>${escapeHTML(fingerprint.tz || '时区待核对')} · 环境代次 ${escapeHTML(row.generation ?? '未提供')}</p></div><span class="env-badge env-${tone}">${escapeHTML(status)}</span></header>
    <div class="env-roles">${roles}</div>
    <div class="env-resources"><div><span>内存配置</span><strong>${escapeHTML(fingerprint.mem === 'unlimited' ? '未限制' : fingerprint.mem || '未提供')}</strong></div><div><span>CLI 版本</span><strong>${escapeHTML((row.cli_versions || []).join(' / ') || '未安装')}</strong></div><div><span>CLI 作业</span><strong>${row.busy ? '执行中' : '当前空闲'}</strong></div></div>
    ${ownership ? `<p class="env-notice" role="status">${escapeHTML(ownership.message)}${ownership.phase !== 'ready' && ['return', 'attach', 'authorize'].includes(ownership.direction) ? action('cancel-credential-return', '取消未提交交接', row.busy) : ''}</p>` : ''}
    ${ui.feedback.has(id) ? `<p class="env-notice" role="status">${escapeHTML(ui.feedback.get(id))}</p>` : ''}
    ${renderNativeKernel(row)}
    ${renderNativePreparation(row)}
    <section class="env-window"><div><h4>当地运行窗口</h4>${row.run_window ? renderAccountRunWindow({id: row.account_id, run_window: row.run_window}) : '<p class="env-muted">运行窗口尚未提供</p>'}</div>${row.run_window && row.account_id != null ? `<button type="button" class="btn btn-sm" data-run-window-config="${escapeHTML(row.account_id)}" data-environment="${escapeHTML(id)}" data-env-focus="${escapeHTML(id + ':window')}">配置时段</button>` : ''}</section>
    <details class="env-details" data-env-details="${escapeHTML(id + ':technical')}"><summary>环境与物理详情</summary><div class="env-details-body"><dl><dt>环境 ID</dt><dd><code>${escapeHTML(id)}</code></dd><dt>主机名</dt><dd>${escapeHTML(fingerprint.hostname || '未提供')}</dd><dt>设备身份</dt><dd>${escapeHTML(row.identity_status || '待核对')}</dd><dt>语言区域</dt><dd>${escapeHTML(fingerprint.lang || '未提供')}</dd><dt>画像版本</dt><dd>${escapeHTML(fingerprint.profile_version ?? '未提供')}</dd></dl>${row.physical_features ? renderPhysicalFeatures(row) : '<p class="env-muted">物理实测尚未采集。</p>'}</div></details>
    <details class="env-details" data-env-details="${escapeHTML(id + ':maintenance')}"><summary>维护操作</summary><div class="env-details-body"><p class="env-muted">停止和重建保留 HOME、身份及证据。画像校正按服务器许可执行。</p><div class="env-actions">${action('stop', '停止环境', row.busy)}${action('rebuild', '重建容器', row.busy)}${action('reconcile', '故障对账', row.busy)}${action('reprofile', '校正画像', !row.can_reprofile)}</div>${row.reprofile_message ? `<p class="env-muted">${escapeHTML(row.reprofile_message)}</p>` : ''}</div></details>
  </article>`;
}

/**
 * 展示最近真实巡检结果，与内核操作的历史预热回执分开呈现。
 * @param {object} row 含原生准备安全摘要的环境。
 * @return {string} 已转义的准备状态区域。
 */
function renderNativePreparation(row) {
  const value = row.native_preparation;
  if (!value) return '';
  const labels = {ready: '热进程就绪', busy: '进程使用中', preparing: '正在准备', unprepared: '等待准备',
    sleeping: '环境休眠', disabled: '账号停用', maintenance: '维护中', failed: '准备失败', unknown: '待检查'};
  const reasons = {identity_changed: '运行身份已变化', worker_unavailable: '进程退出或管道异常',
    check_expired: '最近检查已过期', check_failed: '状态检查失败', preparation_failed: '本地准备失败',
    invalidated: '准备已失效', capability_unknown: '原生能力待核对', binding_unverified: '当前环境代次待核对',
    maintenance: '账号正在维护', sleeping: '环境休眠', disabled: '账号已停用'};
  const tone = value.state === 'ready' ? 'good' : ['busy', 'sleeping', 'disabled'].includes(value.state) ? 'muted' : 'warning';
  const checked = typeof value.checked_at_ms === 'number' && Number.isFinite(value.checked_at_ms)
    ? new Date(value.checked_at_ms).toLocaleString() : '未观测';
  return `<section class="env-preparation" data-native-preparation>
    <div class="env-card-head"><h4>原生准备</h4><span class="env-badge env-${tone}">${escapeHTML(labels[value.state] || '未知状态')}</span></div>
    <div class="env-resources"><div><span>空闲热进程</span><strong>${escapeHTML(value.idle_workers ?? '未观测')}</strong></div><div><span>实际进程数</span><strong>${escapeHTML(value.live_workers ?? '未观测')}</strong></div><div><span>空闲 PID</span><strong>${escapeHTML(value.pid ?? '未观测')}</strong></div></div>
    <p class="env-muted">最近检查：${escapeHTML(checked)}</p>
    ${value.reason ? `<p class="env-notice">${escapeHTML(reasons[value.reason] || '状态待核对')}</p>` : ''}
  </section>`;
}

/**
 * 渲染服务器提供的内核版本、进度和灰度操作能力。
 * @param {object} row 含 native_kernel 的环境摘要。
 * @return {string} 内核管理面板。
 */
function renderNativeKernel(row) {
  const kernel = row.native_kernel, id = row.environment_id;
  if (!kernel) return '<section class="env-kernel env-kernel-unavailable"><h4>请求内核</h4><p>此环境当前未提供在线内核管理。</p></section>';
  const busy = KERNEL_BUSY_STATES.includes(kernel.state) || state.environmentUI.pending.has(id);
  const available = !busy && !row.busy && Object.hasOwn(KERNEL_STATES, kernel.state) && kernel.state !== 'reconcile';
  const version = reference => escapeHTML(reference?.release || '无');
  const button = (operation, label, enabled, digest = '') => `<button type="button" class="btn btn-sm ${operation === 'activate' ? 'btn-primary' : ''}" data-kernel-action="${operation}" data-environment="${escapeHTML(id)}" data-kernel-revision="${escapeHTML(kernel.revision)}" data-kernel-release="${escapeHTML(kernel.prepared?.release || '')}" data-kernel-digest="${escapeHTML(digest)}" data-env-focus="${escapeHTML(id + ':' + operation)}" ${enabled ? '' : 'disabled'}>${label}</button>`;
  return `<section class="env-kernel"><div class="env-section-head"><h4>请求内核</h4><span class="env-tag">在线切换试点</span></div>
    <div class="env-kernel-version"><strong>${version(kernel.current)}</strong><span role="status">${escapeHTML(KERNEL_STATES[kernel.state] || '状态待核对')}</span></div>
    <div class="env-versions"><div><span>已准备候选</span><strong>${version(kernel.prepared)}</strong></div><div><span>上一版本</span><strong>${version(kernel.previous)}</strong></div></div>
    ${kernel.error ? `<p class="env-error" role="alert">${escapeHTML(kernel.error)}</p>` : ''}
    ${row.busy ? '<p class="env-muted">CLI 作业执行中，请在空闲后操作内核。</p>' : ''}
    <div class="env-actions">${button('prepare', '准备内核', available)}${button('activate', '激活候选', available && kernel.prepared && kernel.prepared.launcher_sha256 !== kernel.current?.launcher_sha256, kernel.prepared?.launcher_sha256)}${button('rollback', '回滚内核', available && kernel.previous, kernel.previous?.launcher_sha256)}${kernel.state === 'reconcile' ? button('recover', '恢复对账', !busy && !row.busy) : ''}</div>
    <details class="env-kernel-details" data-env-details="${escapeHTML(id + ':kernel')}"><summary>版本摘要与预热回执</summary><dl><dt>当前分发 SHA256</dt><dd><code>${escapeHTML(kernel.current?.launcher_sha256 || '未提供')}</code></dd><dt>候选分发 SHA256</dt><dd><code>${escapeHTML(kernel.prepared?.launcher_sha256 || '未准备')}</code></dd><dt>上一版分发 SHA256</dt><dd><code>${escapeHTML(kernel.previous?.launcher_sha256 || '无')}</code></dd><dt>上次预热回执 PID</dt><dd>${escapeHTML(kernel.pid ?? '未采集')}</dd><dt>实际映像 SHA256</dt><dd><code>${escapeHTML(kernel.image_sha256 || '未采集')}</code></dd></dl></details>
  </section>`;
}

/**
 * 分派明确点击的内核、实测、时段或维护操作。
 * @param {HTMLButtonElement} button 当前卡片的操作按钮。
 * @return {Promise<void>} 当前动作及状态刷新完成。
 */
async function handleEnvironmentAction(button) {
  const ui = state.environmentUI, id = button.dataset.environment, generation = state.viewGeneration;
  if (!id || ui.pending.has(id)) return;
  if (button.dataset.kernelAction) return openNativeKernelDialog(button);
  if (button.dataset.runWindowConfig) {
    try { await openRunWindowConfig(button.dataset.runWindowConfig); }
    catch (error) {
      if (generation === state.viewGeneration) { ui.feedback.set(id, '加载时段失败：' + error.message); paintEnvironments(); }
    }
    return;
  }
  const operation = button.dataset.operation;
  const physical = button.hasAttribute('data-physical-refresh');
  if (!physical && !['stop', 'rebuild', 'reconcile', 'reprofile', 'cancel-credential-return'].includes(operation)) return;
  if (!physical && !confirm(operation === 'reprofile' ? '画像校正会生成新的环境参数，并保留登录凭据。确认继续？' : '确认在账号空闲时执行此维护操作？持久数据会保留。')) return;
  ui.pending.add(id);
  ui.feedback.delete(id);
  paintEnvironments();
  try {
    await API(`/environments/${encodeURIComponent(id)}/${physical ? 'physical-features/refresh' : 'maintenance'}`, {
      method: 'POST', body: JSON.stringify(physical ? {} : {operation})
    });
    if (generation !== state.viewGeneration || currentTab() !== 'environments') return;
    if (physical) { ui.expanded.add(id + ':technical'); ui.expanded.add(id + ':physical'); }
    ui.feedback.set(id, physical ? '实测已刷新。' : '维护操作已完成。');
  } catch (error) {
    if (generation === state.viewGeneration) ui.feedback.set(id, '操作失败：' + error.message);
  } finally {
    ui.pending.delete(id);
    if (generation === state.viewGeneration && currentTab() === 'environments') await renderEnvironments();
  }
}

/**
 * 打开内核操作窗口，冻结用户看到的版本和前置状态。
 * @param {HTMLButtonElement} button 已显示的内核动作。
 * @return {void}
 */
function openNativeKernelDialog(button) {
  if (state.kernelDialog) return;
  const id = button.dataset.environment;
  const row = state.environmentUI.rows.find(item => item.environment_id === id);
  const operation = button.dataset.kernelAction;
  if (!row?.native_kernel || !['prepare', 'activate', 'rollback', 'recover'].includes(operation)) return;
  const labels = {prepare: '准备内核', activate: '激活候选', rollback: '回滚内核', recover: '恢复对账'};
  const kernel = row.native_kernel;
  const target = operation === 'activate' ? kernel.prepared : operation === 'rollback' ? kernel.previous : null;
  const request = {id, operation, revision: button.dataset.kernelRevision, digest: button.dataset.kernelDigest || null,
    release: operation === 'activate' ? button.dataset.kernelRelease : null, generation: state.viewGeneration,
    focus: button.dataset.envFocus, sending: false};
  state.kernelDialog = request;
  const form = $('#native-kernel-form'), modal = $('#native-kernel-modal');
  form.reset();
  form.elements.release.disabled = operation !== 'prepare';
  $('#native-kernel-release-field').classList.toggle('hidden', operation !== 'prepare');
  $('#native-kernel-title').textContent = labels[operation];
  $('#native-kernel-account').textContent = row.name;
  $('#native-kernel-current').textContent = kernel.current?.release || '待核对';
  $('#native-kernel-target').textContent = operation === 'prepare' ? '按发布标签下载并校验' : target?.release || '按服务器持久状态恢复';
  $('#native-kernel-description').textContent = operation === 'prepare'
    ? '准备期间当前内核继续接单。准备完成后可单独激活候选。'
    : '将等待该账号在途请求结束，完成目标内核的预热与身份核验后继续接单。';
  $('#native-kernel-feedback').textContent = '';
  const submit = $('button[type="submit"]', form);
  submit.textContent = labels[operation];
  submit.disabled = false;
  form.onsubmit = submitNativeKernel;
  modal.onkeydown = event => {
    if (event.key !== 'Tab') return;
    const nodes = $$('button:not(:disabled), input:not(:disabled)', modal).filter(node => node.getClientRects().length);
    const index = nodes.indexOf(document.activeElement);
    if (event.shiftKey && index <= 0) { event.preventDefault(); nodes.at(-1)?.focus(); }
    else if (!event.shiftKey && index === nodes.length - 1) { event.preventDefault(); nodes[0]?.focus(); }
  };
  openModal('#native-kernel-modal');
  (operation === 'prepare' ? form.elements.release : $('button[type="submit"]', form)).focus();
}

/**
 * 关闭窗口并收口当前表单归属；导航强制失效，提交中的普通关窗保持等待。
 * @param {boolean} force 是否由导航强制关闭。
 * @return {boolean} 窗口是否已关闭。
 */
function closeNativeKernelDialog(force = false) {
  const request = state.kernelDialog, modal = $('#native-kernel-modal');
  if (!modal || (request?.sending && !force)) return false;
  state.kernelDialog = null;
  modal.classList.add('hidden');
  modal.onkeydown = null;
  $$('[data-close]', modal).forEach(button => { button.disabled = false; });
  if (request && !force) {
    const trigger = $$('[data-env-focus]').find(node => node.dataset.envFocus === request.focus && !node.disabled);
    (trigger || $('#environment-refresh'))?.focus({preventScroll: true});
  }
  return true;
}

/**
 * 提交冻结的单次内核操作，错误保留在原窗口并要求重新读取状态。
 * @param {SubmitEvent} event 真实表单提交事件。
 * @return {Promise<void>} 操作回执及状态读取完成。
 */
async function submitNativeKernel(event) {
  event.preventDefault();
  const request = state.kernelDialog, ui = state.environmentUI, form = event.currentTarget;
  if (!request || request.sending || request.failed || request.generation !== state.viewGeneration) return;
  const release = request.operation === 'prepare' ? form.elements.release.value.trim() : request.release;
  const random = crypto.getRandomValues(new Uint8Array(16));
  random[6] = (random[6] & 15) | 64;
  random[8] = (random[8] & 63) | 128;
  const hex = Array.from(random, value => value.toString(16).padStart(2, '0')).join('');
  const operation_id = [hex.slice(0,8), hex.slice(8,12), hex.slice(12,16), hex.slice(16,20), hex.slice(20)].join('-');
  request.sending = true;
  form.elements.release.disabled = true;
  $$('[data-close]', $('#native-kernel-modal')).forEach(button => { button.disabled = true; });
  const submit = $('button[type="submit"]', form);
  submit.disabled = true;
  $('#native-kernel-feedback').textContent = '操作已提交，正在等待服务器回执。';
  ui.pending.add(request.id);
  paintEnvironments();
  // 弹窗保存冻结版本，列表的进度刷新只读，不更新已经打开的提交上下文。
  renderEnvironments();
  try {
    await API(`/environments/${encodeURIComponent(request.id)}/native-kernel`, {method: 'POST', body: JSON.stringify({
      operation: request.operation, operation_id, release, expected_sha256: request.digest, expected_revision: request.revision
    })});
    if (state.kernelDialog !== request) return;
    request.sending = false;
    closeModal('#native-kernel-modal');
    ui.feedback.set(request.id, '内核操作已完成，版本以最新读取状态为准。');
  } catch (error) {
    if (state.kernelDialog !== request) return;
    request.failed = true;
    $('#native-kernel-feedback').textContent = '内核操作失败：' + error.message + '。请关闭窗口并刷新环境状态后重新操作。';
  } finally {
    request.sending = false;
    if (state.kernelDialog === request) $$('[data-close]', $('#native-kernel-modal')).forEach(button => { button.disabled = false; });
    ui.pending.delete(request.id);
    if (request.generation === state.viewGeneration && currentTab() === 'environments') await renderEnvironments();
  }
}
/**
 * 按字段实际口径显示配置与观察值，零 RAM 仅表示明确无限制。
 * @param {string} key 字段名
 * @param {*} value 已校验的公开标量
 * @return {string} 供转义后展示的文本
 */
function physicalFeatureValue(key, value) {
  if (value == null) return '未采集';
  if (typeof value === 'boolean') return value ? '有' : '无';
  if (key.endsWith('_bytes')) return value === 0 ? '未限制' : `${(value / 1024 ** 2).toFixed(0)} MiB`;
  return String(value);
}

/**
 * 展示保存配置和上次容器实测，避免将缓存值描述为实时采集。
 * @param {Object} row 环境公开摘要
 * @return {string} 已转义的详情 HTML
 */
function renderPhysicalFeatures(row) {
  const features = row.physical_features;
  if (!features) return '';
  const statuses = {match: '一致', mismatch: '有差异', observed: '已采集', unobserved: '未采集', stale: '旧代观察'};
  const observed = features.observed_at ? new Date(features.observed_at * 1000).toLocaleString('zh-CN') : '未采集';
  return `<details class="physical-features" data-physical-details="${escapeHTML(row.environment_id)}" data-env-details="${escapeHTML(row.environment_id + ':physical')}">
    <summary>物理特征 · ${escapeHTML(observed)}</summary>
    <p class="hint">${escapeHTML(features.message)}。实测取自 CLI 容器可见环境，资源按实际限制展示。</p>
    <button type="button" class="btn btn-sm" data-physical-refresh="${escapeHTML(row.environment_id)}" data-environment="${escapeHTML(row.environment_id)}" data-env-focus="${escapeHTML(row.environment_id + ':physical-refresh')}"
      ${row.busy || state.environmentUI.pending.has(row.environment_id) || row.role_status?.cli !== 'running' ? 'disabled' : ''}>刷新实测</button>
    <div class="physical-table-wrap"><table class="data physical-table">
      <thead><tr><th>特征</th><th>保存配置</th><th>容器实测</th><th>对照</th></tr></thead>
      <tbody>${features.fields.map(field => `<tr>
        <th>${escapeHTML(field.label)}</th>
        <td>${escapeHTML(field.configured == null ? '无对应配置' : physicalFeatureValue(field.key, field.configured))}</td>
        <td>${escapeHTML(physicalFeatureValue(field.key, field.observed))}</td>
        <td>${escapeHTML(statuses[field.status] || '未采集')}</td>
      </tr>`).join('')}</tbody>
    </table></div>
  </details>`;
}

