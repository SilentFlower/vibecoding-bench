/** 账号环境视图；与主后台共享视觉，操作沿用既有管理合同。 */
const ENVIRONMENT_STATES = {ready: '就绪', stopped: '已停止', starting: '启动中',
  reconcile: '待对账', cli_reconcile: 'CLI 待对账', profile_reauth: '画像授权中',
  profile_reauth_reconcile: '画像待对账'};
const KERNEL_STATES = {idle: '可准备', preparing: '正在下载并校验', draining: '等待在途请求结束',
  switching: '预热候选', restoring: '恢复原版', finishing: '核对并开放接单', active: '已生效',
  failed: '保持原版', restored: '已恢复原版', reconcile: '待对账'};
const KERNEL_BUSY_STATES = ['preparing', 'draining', 'switching', 'restoring', 'finishing'];

/** 汇总各版内核状态，保护账号共享维护门禁。@param {object} row 环境快照。@return {string[]} 状态集合。 */
function kernelStates(row) {
  return Object.values(row.native_kernels || {'2.1.293': row.native_kernel}).map(value => value?.state);
}
const CRIU_STATES = {disabled: '已关闭', not_installed: '镜像待升级', requires_rebuild: '待应用',
  preparing: '模板准备中', ready: '模板已就绪', unavailable: '当前使用普通启动', unknown: '状态待核对'};
const CRIU_REASONS = {legacy_backend: '当前为普通发送后端', platform_disabled: '平台已关闭加速',
  account_disabled: '账号已手动关闭', image_unsupported: '当前账号镜像尚未安装恢复器',
  memory_budget: '当前发送器内存额度不足以恢复，继续普通启动', container_rebuild_required: '空闲应用设置后启用恢复入口',
  controller_preflight_failed: '恢复环境预检失败，继续普通启动', controller_unavailable: '恢复器暂不可用',
  kernel_unsupported: '当前内核尚未支持恢复，请选择配套新版', template_failed: '模板准备失败，正在退避',
  template_preparing: '后台正在准备零模型模板', telemetry_missing: '当前版本尚未提供恢复状态',
  telemetry_stale: '状态已过期，等待同代巡检', binding_unverified: '环境绑定待核对',
  identity_changed: '账号身份已变化，等待重新准备', environment_stopped: '环境已停止', read_failed: '恢复状态读取失败'};

/** 使旧列表回执和本页轮询失效，后台已提交操作继续由原所有者收口。@return {void} */
function leaveEnvironments() {
  const ui = state.environmentUI;
  ui.request += 1;
  clearTimeout(ui.timer);
  ui.timer = null;
  ui.openedLocation = null;
  closeEnvironmentWorkspace(true);
  closeNativeKernelDialog(true);
  closeCpuResourceDialog(true);
  closeContentCaptureDialog(true);
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
    const parameters = new URLSearchParams(location.hash.split('?')[1] || '');
    const section = parameters.get('section');
    if (section && ['overview','resources','kernel','schedule','maintenance'].includes(section) && ui.openedLocation !== location.hash) {
      const target = rows.find(row => parameters.get('environment') ? row.environment_id === parameters.get('environment')
        : parameters.has('gateway_account') && String(row.gateway_account_id) === parameters.get('gateway_account'));
      const button = target && $$('[data-env-open]', $('#environment-list')).find(node => node.dataset.environment === target.environment_id && node.dataset.envOpen === section);
      if (button) { ui.openedLocation = location.hash; openEnvironmentWorkspace(button); }
    }
  } catch (error) {
    if (!current()) return;
    $('#environment-feedback').textContent = '读取环境失败：' + error.message + (ui.loaded ? '。当前展示上次读取结果。' : '。请点击刷新重试。');
    if (!ui.loaded) $('#environment-list').innerHTML = '<p class="env-empty">环境数据读取失败，请刷新重试。</p>';
  } finally {
    if (current()) {
      refresh.disabled = false;
      // 操作期间只串行读取状态；离页立即释放定时器，避免迟到回执污染下一页。
      if (ui.pending.size || ui.rows.some(row => kernelStates(row).some(value => KERNEL_BUSY_STATES.includes(value))
          || row.native_preparation?.checking === true || row.native_preparation?.state === 'preparing'
          || row.native_preparation?.reason === 'backend_pending')) {
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
  patchRuntimeContent($('#environment-summary'), [['all','全部环境',counts[0]],['ready','就绪',counts[1]],['attention','需要关注',ui.rows.filter(row=>!['ready','stopped'].includes(row.state)).length],['stopped','已停止',counts[2]]].map(([value,label,count]) => `<button type="button" data-environment-filter="${value}" class="tab ${ui.status===value?'active':''}" aria-pressed="${ui.status===value}">${label}<span>${count}</span></button>`).join(''));
  $('#environment-summary').onclick = event => {const button=event.target.closest('[data-environment-filter]');if(button){ui.status=button.dataset.environmentFilter;paintEnvironments();}};
  const statuses = new Set(ui.rows.map(row => row.state || 'unknown'));
  if (ui.status !== 'all') statuses.add(ui.status);
  const select = $('#environment-status');
  const options = '<option value="all">全部状态</option>' + [...statuses].sort().map(value =>
    `<option value="${escapeHTML(value)}" ${ui.status === value ? 'selected' : ''}>${escapeHTML(ENVIRONMENT_STATES[value] || `未知状态：${value}`)}</option>`).join('');
  if (document.activeElement !== select && select.innerHTML !== options) select.innerHTML = options;
  select.value = ui.status;
  const query = ui.query.trim().toLocaleLowerCase();
  const parameters = new URLSearchParams(location.hash.split('?')[1] || '');
  const gateway = parameters.get('gateway_account'), environment = parameters.get('environment');
  const rows = ui.rows.filter(row => (!gateway || String(row.gateway_account_id) === gateway)
    && (!environment || row.environment_id === environment)
    && (ui.status === 'all' || (ui.status === 'attention' ? !['ready','stopped'].includes(row.state) : (row.state || 'unknown') === ui.status))
    && `${row.name || ''} ${row.environment_id || ''}`.toLocaleLowerCase().includes(query));
  $('#environment-result-count').textContent = `显示 ${rows.length} / ${ui.rows.length} 个环境${gateway ? ` · 网关账号 ${gateway}` : ''}`;
  $('#environment-clear-target').hidden = !gateway && !environment;
  patchRuntimeContent(list, rows.map(renderEnvironmentCard).join('') || `<p class="env-empty">${ui.rows.length ? '没有匹配的环境，请调整搜索或筛选。' : '暂无账号环境。'}</p>`);
  $$('details[data-env-details]', list).forEach(details => {
    details.open = ui.expanded.has(details.dataset.envDetails);
    details.ontoggle = () => {
      if (!details.isConnected) return;
      if (details.open) ui.expanded.add(details.dataset.envDetails);
      else ui.expanded.delete(details.dataset.envDetails);
    };
  });
  paintEnvironmentWorkspace();
  if (focus) $$('[data-env-focus]', list).find(node => node.dataset.envFocus === focus)?.focus({preventScroll: true});
}

/**
 * 按实际环境字段展示摘要及独立维护入口。
 * @param {object} row 服务器公开环境摘要。
 * @return {string} 已转义的账号卡片。
 */
function renderEnvironmentDetailCard(row) {
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
  return `<article class="env-detail-pane" aria-label="${escapeHTML(row.name || '未命名环境')}">
    <header class="env-card-head"><div><h3>${escapeHTML(row.name || '未命名环境')}</h3><p>${escapeHTML(fingerprint.tz || '时区待核对')} · 环境代次 ${escapeHTML(row.generation ?? '未提供')}</p></div><span class="env-badge env-${tone}">${escapeHTML(status)}</span></header>
    <div class="env-roles">${roles}</div>
    <div class="env-resources"><div><span>内存配置</span><strong>${escapeHTML(fingerprint.mem === 'unlimited' ? '未限制' : fingerprint.mem || '未提供')}</strong></div><div><span>CLI 版本</span><strong>${escapeHTML((row.cli_versions || []).join(' / ') || '未安装')}</strong></div><div><span>CLI 作业</span><strong>${row.busy ? '执行中' : '当前空闲'}</strong></div></div>
    ${ownership ? `<p class="env-notice" role="status">${escapeHTML(ownership.message)}${ownership.phase !== 'ready' && ['return', 'attach', 'authorize'].includes(ownership.direction) ? action('cancel-credential-return', '取消未提交交接', row.busy) : ''}</p>` : ''}
    ${ui.feedback.has(id) ? `<p class="env-notice" role="status">${escapeHTML(ui.feedback.get(id))}</p>` : ''}
    ${renderNativeKernel(row)}
    ${renderNativePreparation(row)}
    ${renderEnvironmentCriu(row, pending)}
    <section class="env-window"><div><h4>请求内容采集</h4><p class="env-muted">${row.content_capture?.applied ? (row.content_capture.enabled ? '已开启' : '已关闭') : '实际配置待核对'} · 默认开启 · debug 保存脱敏原文</p><p class="env-muted">${escapeHTML(nativeRuntimePending(row) ? '原生 TLS 采集：等待原生环境准备' : tlsCaptureDescription(row.content_capture?.tls_observer))}</p></div><button type="button" class="env-switch" role="switch" aria-label="${escapeHTML((row.name || '当前环境') + '请求内容采集')}" aria-checked="${row.content_capture?.enabled === true}" data-content-capture data-environment="${escapeHTML(id)}" data-env-focus="${escapeHTML(id + ':capture')}" ${pending || row.busy || kernelStates(row).some(value => KERNEL_BUSY_STATES.includes(value)) || kernelStates(row).includes('reconcile') || !['ready', 'stopped'].includes(row.state) || !row.content_capture?.supported || !row.content_capture?.applied ? 'disabled' : ''}><span></span></button></section>
    ${row.isolation_version === 2 ? `<section class="env-window"><div><h4>CPU 额度</h4><p class="env-muted">分别调整 CLI、API 发送器和网络的额度，保存后重建沿用。</p></div><button type="button" class="btn btn-sm" data-cpu-resources data-environment="${escapeHTML(id)}" data-env-focus="${escapeHTML(id + ':cpu')}" ${pending ? 'disabled' : ''}>调整额度</button></section>` : ''}
    <section class="env-window"><div><h4>当地运行窗口</h4>${row.run_window ? renderAccountRunWindow({id: row.account_id, run_window: row.run_window}) : '<p class="env-muted">运行窗口尚未提供</p>'}</div>${row.run_window && row.account_id != null ? `<button type="button" class="btn btn-sm" data-run-window-config="${escapeHTML(row.account_id)}" data-environment="${escapeHTML(id)}" data-env-focus="${escapeHTML(id + ':window')}">配置时段</button>` : ''}</section>
    <details class="env-details" data-env-details="${escapeHTML(id + ':technical')}"><summary>环境与物理详情</summary><div class="env-details-body"><dl><dt>环境 ID</dt><dd><code>${escapeHTML(id)}</code></dd><dt>主机名</dt><dd>${escapeHTML(fingerprint.hostname || '未提供')}</dd><dt>设备身份</dt><dd>${escapeHTML(row.identity_status || '待核对')}</dd><dt>语言区域</dt><dd>${escapeHTML(fingerprint.lang || '未提供')}</dd><dt>画像版本</dt><dd>${escapeHTML(fingerprint.profile_version ?? '未提供')}</dd></dl>${row.physical_features ? renderPhysicalFeatures(row) : '<p class="env-muted">物理实测尚未采集。</p>'}</div></details>
    <details class="env-details" data-env-details="${escapeHTML(id + ':maintenance')}"><summary>维护操作</summary><div class="env-details-body"><p class="env-muted">停止和重建保留 HOME、身份及证据。画像校正按服务器许可执行。</p><div class="env-actions">${action('stop', '停止环境', row.busy)}${action('rebuild', '重建容器', row.busy)}${action('reconcile', '故障对账', row.busy)}${action('reprofile', '校正画像', !row.can_reprofile)}</div>${row.reprofile_message ? `<p class="env-muted">${escapeHTML(row.reprofile_message)}</p>` : ''}</div></details>
  </article>`;
}


/** 按真实环境摘要绘制定稿卡片，未观测值保持未知。@param {object} row 环境。@return {string} 卡片。 */
function renderEnvironmentCard(row) {
 const cpu=state.environmentUI.cpuSnapshots?.get(row.environment_id)?.cpus;
 const id=escapeHTML(row.environment_id),name=escapeHTML(row.name||'未命名环境'),fp=row.fingerprint||{},prep=row.native_preparation;
 const roleLabels={running:'运行中',exited:'已退出',stopped:'已停止',created:'已创建',restarting:'重启中',missing:'未创建'};
 const tone=row.state==='ready'?'healthy':row.state==='stopped'?'muted':'warning';
 const open=(tab,label,extra='')=>`<button type="button" data-env-open="${tab}" data-environment="${id}" ${extra}>${label}</button>`;
 return `<article class="env-card environment environment-rich" data-runtime-key="${id}" aria-label="${name}">
  <header class="environment-card-head"><span class="environment-avatar"><svg class="runtime-icon"><use href="approved-icons.svg#i-box"></use></svg></span><div class="environment-identity"><h3>${name}</h3><span>${row.gateway_account_id!=null?'网关账号 #'+escapeHTML(row.gateway_account_id):row.account_id!=null?'任务账号 #'+escapeHTML(row.account_id):'待提交的授权环境'}</span></div><span class="environment-status ${tone}"><i></i>${escapeHTML(ENVIRONMENT_STATES[row.state]||'未知状态：'+(row.state||'未提供'))}</span></header>
  <div class="environment-id"><code>${id}</code><span>第 ${escapeHTML(row.generation??'未知')} 代</span></div>
  <div class="environment-role-strip">${[['cli','CLI'],['sender','发送器'],['network','网络']].map(([role,label])=>`<div class="${row.role_status?.[role]==='running'?'running':''}"><i></i><span>${label}</span><strong>${escapeHTML(roleLabels[row.role_status?.[role]]||'未知')}</strong></div>`).join('')}</div>
  <div class="environment-resources-grid"><div><span>内存配置</span><strong>${escapeHTML(fp.mem==='unlimited'?'未限制':fp.mem||'未提供')}</strong></div><div><span>CLI CPU</span><strong>${escapeHTML(cpu?.cli??'未采集')}<small>${cpu?.cli!=null?' 核':''}</small></strong></div><div><span>发送器 CPU</span><strong>${escapeHTML(cpu?.sender??'未采集')}<small>${cpu?.sender!=null?' 核':''}</small></strong></div><div><span>网络 CPU</span><strong>${escapeHTML(cpu?.network??'未采集')}<small>${cpu?.network!=null?' 核':''}</small></strong></div></div>
  <div class="environment-version-line"><span>CLI <strong>${escapeHTML((row.cli_versions||[]).join(' / ')||'未安装')}</strong></span>${open('kernel','内核 <strong>'+escapeHTML(row.native_kernel?.current?.release||'未提供')+'</strong> ›')}</div>
  <section class="environment-readiness ${tone==='healthy'?'':tone}"><div><strong>${escapeHTML(({ready:'热进程就绪',busy:'进程使用中',preparing:'正在准备',unprepared:'等待准备',sleeping:'环境休眠',disabled:'常规请求通道',failed:'准备失败'})[prep?.state]||'准备状态待核对')}</strong><span class="environment-job">${row.busy?'CLI 作业执行中':'CLI 作业空闲'}</span></div><p>293 空闲暖进程 <b>${escapeHTML(prep?.idle_workers??'—')}</b> / 存活 <b>${escapeHTML(prep?.live_workers??'—')}</b> · 空闲 PID ${escapeHTML(prep?.pid??'未观测')}</p></section>
  <div class="environment-feature-row">${open('resources','<span>CRIU 加速</span><strong>'+escapeHTML(CRIU_STATES[row.criu?.state]||'待核对')+'</strong>')}${open('resources','<span>内容采集</span><strong>'+(row.content_capture?.applied?(row.content_capture.enabled?'已开启':'已关闭'):'待核对')+'</strong>')}</div>
  ${open('schedule','<span>'+escapeHTML(row.run_window?.message||'运行时段尚未提供')+' <small>'+escapeHTML(fp.tz||'')+'</small></span> ›','class="environment-schedule-summary"')}
  ${state.environmentUI.feedback.has(row.environment_id)?`<p class="env-notice" role="status">${escapeHTML(state.environmentUI.feedback.get(row.environment_id))}</p>`:''}
  <footer class="environment-card-actions">${open('overview',runtimeIcon('box')+'环境详情')}${open('resources',runtimeIcon('settings')+'资源配置')}${open('kernel',runtimeIcon('spark')+'内核管理')}${open('maintenance',runtimeIcon('shield')+'维护')}</footer>
 </article>`;
}
let environmentWorkspace=null;
/** 打开同一环境工作区；各分类共享同一DOM。@param {HTMLElement} button 入口。@return {void} */
function openEnvironmentWorkspace(button) {
 const id=button.dataset.environment,row=state.environmentUI.rows.find(item=>item.environment_id===id);if(!row)return;
 environmentWorkspace={id,tab:button.dataset.envOpen||'overview',opener:button};
 $('#environment-workspace').onkeydown=event=>{
  if(event.key!=='Tab')return;
  const nodes=$$('button:not(:disabled),input:not(:disabled),a[href],summary',$('#environment-workspace')).filter(node=>node.getClientRects().length),index=nodes.indexOf(document.activeElement);
  if(event.shiftKey&&index<=0){event.preventDefault();nodes.at(-1)?.focus();}
  else if(!event.shiftKey&&index===nodes.length-1){event.preventDefault();nodes[0]?.focus();}
 };

 $('#environment-workspace-title').textContent='环境管理';
 paintEnvironmentWorkspace();openModal('#environment-workspace');$('#environment-workspace [data-close]').focus();
}
/** 关闭工作区并恢复原焦点。@return {void} */
function closeEnvironmentWorkspace(force=false) {
 if((state.cpuDialog?.inline&&state.cpuDialog.sending||state.runWindowConfig?.inline&&state.runWindowConfig.sending)&&!force)return false;
 const context=environmentWorkspace;environmentWorkspace=null;
 $('#environment-workspace')?.classList.add('hidden');
 if(state.cpuDialog?.inline)closeCpuResourceDialog(true);
 if(state.runWindowConfig?.inline)closeRunWindowConfig(true);
 if(context?.opener?.isConnected)context.opener.focus({preventScroll:true});
}
/** 更新服务器摘要，页签和已有独立编辑草稿由各自所有者保留。@return {void} */
function paintEnvironmentWorkspace() {
 if(!environmentWorkspace)return;
 const row=state.environmentUI.rows.find(item=>item.environment_id===environmentWorkspace.id);if(!row){closeEnvironmentWorkspace(true);return;}
 const currentContent=$('#environment-workspace-body');if(!currentContent)return;
 let content=document.createElement('div');
 const previousFocus=currentContent.contains(document.activeElement)?document.activeElement:null;
 const focus=previousFocus?.dataset.envFocus;
 // 轮询重绘只更新摘要，已经挂载的资源表单保留同一节点和冻结版本。
 const inlineForm=state.cpuDialog?.inline&&state.cpuDialog.id===row.environment_id?$('#cpu-resource-form'):null;

 const scheduleForm=state.runWindowConfig?.inline?$('#run-window-form'):null;
 const context=$('#environment-workspace-context'),status=ENVIRONMENT_STATES[row.state]||'未知状态：'+(row.state||'未提供');
 patchRuntimeContent(context,`<span class="initial">${runtimeIcon('box')}</span><div><strong>${escapeHTML(row.name||'未命名环境')}</strong><p>${row.gateway_account_id!=null?'网关账号 #'+escapeHTML(row.gateway_account_id):row.account_id!=null?'任务账号 #'+escapeHTML(row.account_id):'待提交的授权环境'} · 第 ${escapeHTML(row.generation??'未知')} 代</p></div><span class="status-dot ${row.state==='ready'?'':'off'}">${escapeHTML(status)}</span>`);
 const labels={overview:['运行概览','当前环境状态与运行组件'],resources:['资源与采集','在这里调整额度、内容采集与加速设置'],kernel:['请求内核','检查版本、准备候选并选择维护动作'],schedule:['运行时段','按账号当地时间安排工作窗口'],maintenance:['维护操作','选择操作后确认影响，当前环境信息持续保留']};
 content.innerHTML=Object.entries(labels).map(([key,[title,note]])=>`<section id="environment-section-${key}" data-workspace-section="${key}" role="tabpanel"><div class="workspace-section-heading"><h3>${title}</h3><p>${note}</p></div><div data-section-body="${key}"></div></section>`).join('');
 const scratch=document.createElement('div');scratch.innerHTML=renderEnvironmentDetailCard(row);
 for(const node of [...scratch.firstElementChild.children]){
  let tab='overview';
  if(node.matches('header'))continue;
  if(node.classList.contains('env-kernel'))tab='kernel';
  if(node.classList.contains('env-window'))tab=node.querySelector('[data-run-window-config]')?'schedule':'resources';
  if(node.dataset.envDetails?.endsWith(':maintenance'))tab='maintenance';
  if(node.querySelector('[data-cpu-resources]'))node.classList.add('environment-cpu-section');
  content.querySelector(`[data-section-body="${tab}"]`).append(node);
  if(node.matches('details.env-details'))node.open=state.environmentUI.expanded.has(node.dataset.envDetails);
 }
 const overview=content.querySelector('[data-section-body=overview]');
 const additional=document.createElement('details');additional.className='environment-observations';additional.dataset.envDetails=row.environment_id+':observations';additional.innerHTML='<summary>运行组件与准备详情</summary>';
 for(const node of [...overview.children])if(node.matches('.env-roles,.env-resources,.env-preparation'))additional.append(node);
 overview.prepend(additional);
 const cpu=state.environmentUI.cpuSnapshots?.get(row.environment_id)?.cpus;
 const prepLabel=({ready:'原生准备就绪',busy:'暖进程使用中',preparing:'原生准备中',failed:'原生准备失败',unknown:'准备状态待检查',disabled:'使用原有转发'})[row.native_preparation?.state]||'状态待核对';
 const feature=value=>value?.applied===true?(value.enabled?'已生效':'已关闭'):value?.applied===false?'待应用':'状态未知';
 const metrics=`<div class="environment-dialog-stats"><div><span>CPU 额度</span><strong>${cpu?.cli!=null?escapeHTML(cpu.cli)+' 核':'未采集'}</strong></div><div><span>CRIU 加速</span><strong>${feature(row.criu)}</strong></div><div><span>内容采集</span><strong>${feature(row.content_capture)}</strong></div></div>`;
 const fields=[['CLI 版本',(row.cli_versions||[]).join(' / ')||'未安装'],['请求内核',row.native_kernel?.current?.release||'未提供'],['环境状态',status+' · '+(row.busy?'CLI 作业执行中':'CLI 作业空闲')],['原生准备',prepLabel]];
 const properties='<div class="workspace-properties">'+fields.map(([label,value])=>`<div class="kv"><span>${label}</span><strong>${escapeHTML(value)}</strong></div>`).join('')+'</div>';
 const disabled=row.busy||state.environmentUI.pending.has(row.environment_id)||row.role_status?.cli!=='running';
 overview.insertAdjacentHTML('afterbegin',metrics+properties+`<div class="workspace-inline-actions"><button type="button" class="btn" data-physical-refresh="${escapeHTML(row.environment_id)}" data-environment="${escapeHTML(row.environment_id)}" ${disabled?'disabled':''}>${runtimeIcon('refresh')}刷新物理实测</button><button type="button" class="btn" data-env-tab="resources">调整资源与采集 ${runtimeIcon('arrow')}</button></div>`);
 const maintenance=content.querySelector('[data-section-body=maintenance]'),actions=[...maintenance.querySelectorAll('[data-operation]')];
 const descriptions={stop:'暂停该环境的运行，保留持久数据',rebuild:'保留账号数据并重新准备运行容器',reconcile:'核对服务端操作与环境状态',reprofile:row.reprofile_message||'按服务端许可更新环境画像'};
 if(actions.length){maintenance.innerHTML='';for(const button of actions){const item=document.createElement('div');item.className='maintenance-option';item.innerHTML=`<div><strong>${escapeHTML(button.textContent)}</strong><p>${escapeHTML(descriptions[button.dataset.operation]||'按服务器许可执行')}</p></div>`;item.append(button);maintenance.append(item);}}
 const resourceBody=content.querySelector('[data-section-body=resources]');
 const cpuSection=resourceBody.querySelector('.environment-cpu-section');
 if(cpuSection){resourceBody.prepend(cpuSection);const host=document.createElement('div');host.id='environment-resource-editor';host.dataset.runtimePreserve='';cpuSection.append(host);if(inlineForm){cpuSection.classList.add('editing');}}
 const scheduleBody=content.querySelector('[data-section-body=schedule]');if(scheduleBody.querySelector('[data-run-window-config]')){const host=document.createElement('div');host.id='environment-schedule-editor';host.dataset.runtimePreserve='';scheduleBody.append(host);if(scheduleForm){scheduleBody.classList.add('editing');}}
 patchRuntimeContent(currentContent,content.innerHTML);content=currentContent;
 content.onclick=event=>{const button=event.target.closest('button');if(!button||button.disabled)return;if(button.dataset.envTab){environmentWorkspace.tab=button.dataset.envTab;applyEnvironmentWorkspaceTab();return;}handleEnvironmentAction(button);};
 for(const details of $$('details[data-env-details]',content)){
  if(details.dataset.envDetails.endsWith(':maintenance'))continue;
  details.open=state.environmentUI.expanded.has(details.dataset.envDetails);
  details.ontoggle=()=>{if(!details.isConnected)return;if(details.open)state.environmentUI.expanded.add(details.dataset.envDetails);else state.environmentUI.expanded.delete(details.dataset.envDetails);};
 }
 const tabs=$('#environment-workspace-tabs');tabs.onclick=event=>{const button=event.target.closest('[data-env-tab]');if(button){environmentWorkspace.tab=button.dataset.envTab;applyEnvironmentWorkspaceTab();}};
 applyEnvironmentWorkspaceTab();
 if(previousFocus?.isConnected)previousFocus.focus({preventScroll:true});
 else if(focus)$$('[data-env-focus]',content).find(node=>node.dataset.envFocus===focus)?.focus({preventScroll:true});
}
/** 切换可见区块，保留资源草稿及同一表单节点。@return {void} */
function applyEnvironmentWorkspaceTab(){
 const tab=environmentWorkspace?.tab;if(!tab)return;
 $$('[data-workspace-section]',$('#environment-workspace-body')).forEach(node=>{node.hidden=node.dataset.workspaceSection!==tab;});
 $$('[data-env-tab]',$('#environment-workspace-tabs')).forEach(button=>{button.classList.toggle('active',button.dataset.envTab===tab);button.setAttribute('aria-selected',String(button.dataset.envTab===tab));});
 if(tab==='schedule'&&!environmentWorkspace.scheduleRequested&&!state.runWindowConfig){const button=$('#environment-section-schedule [data-run-window-config]');if(button&&!button.disabled){environmentWorkspace.scheduleRequested=true;void openRunWindowConfig(button.dataset.runWindowConfig).catch(error=>{if(environmentWorkspace)notifyRuntime('读取运行时段失败：'+error.message);});}}
 if(tab==='resources'&&!environmentWorkspace.cpuRequested&&!state.cpuDialog){const button=$('#environment-resource-editor')?.closest('.environment-cpu-section')?.querySelector('[data-cpu-resources]');if(button&&!button.disabled){environmentWorkspace.cpuRequested=true;void openCpuResourceDialog(button);}}
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
    invalidated: '准备已失效', capability_unknown: '原生能力待核对', binding_unverified: '最近快照属于其他环境或内核代次，等待当前代次检查',
    read_failed: '准备状态读取失败', snapshot_missing: '尚未收到本账号的准备快照',
    snapshot_pending: '等待首次检查返回当前环境快照',
    backend_pending: '已选择原生运行时，等待环境准备',
    native_sender_budget_missing: '原生发送器内存预算尚未配置，请配置后重试',
    native_sender_budget_insufficient: '原生发送器内存预算不足以覆盖当前并发，请调整后重试',
    account_memory_insufficient: '账号总内存不足以容纳网络、原生发送器和 CLI，请调整后重试',
    maintenance: '账号正在维护', system_maintenance: '平台更新中，结束后自动准备', sleeping: '环境休眠', disabled: '账号已停用'};
  const tone = value.state === 'ready' ? 'good' : ['busy', 'sleeping', 'disabled'].includes(value.state) ? 'muted' : 'warning';
  const checked = typeof value.checked_at_ms === 'number' && Number.isFinite(value.checked_at_ms)
    ? new Date(value.checked_at_ms).toLocaleString() : '未观测';
  const pending = ['snapshot_pending', 'snapshot_missing'].includes(value.reason);
  const label = value.state === 'unknown' ? (pending ? (value.checking === true ? '正在检查' : '等待快照')
    : value.reason === 'check_expired' ? '检查已过期' : '状态待核对') : labels[value.state] || '未知状态';
  return `<section class="env-preparation" data-native-preparation>
    <div class="env-card-head"><h4>原生准备</h4><span class="env-badge env-${tone}">${escapeHTML(label)}</span></div>
    <div class="env-resources"><div><span>293 空闲热进程</span><strong>${escapeHTML(value.idle_workers ?? '未观测')}</strong></div><div><span>293 实际进程数</span><strong>${escapeHTML(value.live_workers ?? '未观测')}</strong></div><div><span>空闲 PID</span><strong>${escapeHTML(value.pid ?? '未观测')}</strong></div></div>
    <p class="env-muted">最近检查：${escapeHTML(checked)}</p>
    ${value.versions ? '<div class="env-resources">' + Object.entries(value.versions).filter(([version]) => ['2.1.280', '2.1.293'].includes(version)).map(([version, item]) => `<div><span>${escapeHTML(version)} 运行时</span><strong>${escapeHTML(labels[item?.state] || '状态待核对')}</strong></div>`).join('') + '</div>' : ''}
    ${value.checking === true ? '<p class="env-muted">后台正在检查。页面每20秒自动读取检查结果。</p>' : ''}
    ${typeof value.adaptive_prewarm === 'boolean' ? `<p class="env-muted">并发备用：${value.adaptive_prewarm ? '已启用第二进程补位' : '未启用，保留一个常驻热进程'}。超出已就绪热容量时按需扩容。</p>` : ''}
    ${value.reason ? `<p class="env-notice">${escapeHTML(reasons[value.reason] || '状态待核对')}</p>` : ''}
    ${row.request_backend === 'native293' && ['failed', 'unknown', 'unprepared', 'sleeping'].includes(value.state)
      ? `<button type="button" class="btn btn-sm" data-native-prepare data-environment="${escapeHTML(row.environment_id)}" ${state.environmentUI.pending.has(row.environment_id) || row.busy || !['ready', 'stopped'].includes(row.state) ? 'disabled' : ''}>重试原生准备</button>` : ''}
  </section>`;
}

/** 判断目标已为原生而实际发送器仍待应用。@param {object} row 环境快照。@return {boolean} 是否等待布局准备。 */
function nativeRuntimePending(row) {
  return row.request_backend === 'native293' && row.criu?.supported === false;
}

/** 明确重试当前账号准备，离页后忽略旧回执。@param {HTMLButtonElement} button 重试按钮。@return {Promise<void>} 入队并刷新。 */
async function retryNativePreparation(button) {
  const ui = state.environmentUI, id = button.dataset.environment, generation = state.viewGeneration;
  ui.pending.add(id);
  ui.feedback.delete(id);
  paintEnvironments();
  try {
    await API(`/environments/${encodeURIComponent(id)}/native-preparation`, {method: 'POST', body: '{}'});
    if (generation !== state.viewGeneration || currentTab() !== 'environments') return;
    ui.feedback.set(id, '已安排后台原生准备。');
  } catch (error) {
    if (generation === state.viewGeneration && currentTab() === 'environments') ui.feedback.set(id, '安排原生准备失败：' + error.message);
  } finally {
    ui.pending.delete(id);
    if (generation === state.viewGeneration && currentTab() === 'environments') await renderEnvironments();
  }
}

/** 展示期望选择、实际入口与模板状态。@param {object} row 环境快照。@param {boolean} pending 操作中。@return {string} 加速配置区。 */
function renderEnvironmentCriu(row, pending) {
  const value = row.criu;
  if (!value && !row.native_preparation && !row.native_kernel) return '';
  const enabled = value?.enabled, known = typeof enabled === 'boolean';
  const target = value?.applied === false ? enabled : !enabled;
  const label = value?.applied === false ? (enabled ? '应用开启' : '应用关闭') : (enabled ? '关闭加速' : '开启加速');
  const disabled = pending || row.busy || !known || value?.supported !== true || (!value.platform_enabled && target)
    || !['ready', 'stopped'].includes(row.state) || kernelStates(row).some(value => KERNEL_BUSY_STATES.includes(value)) || kernelStates(row).includes('reconcile');
  const memory = value?.reason === 'memory_budget' ? ` · 当前 ${value.memory_mib} MiB，恢复需 ${value.required_memory_mib} MiB` : '';
  const source = value?.last_start_source === 'criu_restore' ? ' · 最近扩容使用CRIU恢复' : value?.last_start_source === 'exec' ? ' · 最近扩容使用普通启动' : '';
  return `<section class="env-window"><div><h4>CRIU 加速</h4><p class="env-muted">${known ? (enabled ? '自动开启' : '手动关闭') : '选择待核对'} · ${escapeHTML(CRIU_STATES[value?.state] || '状态待核对')}</p><p class="env-muted">${escapeHTML((nativeRuntimePending(row) ? '已选择原生运行时，等待环境准备' : CRIU_REASONS[value?.reason] || (value?.state === 'ready' ? '同账号热模板可用于新进程恢复' : '等待恢复状态采样')) + memory + source)}</p></div><button type="button" class="env-switch" role="switch" aria-label="${label}" aria-checked="${enabled === true}" data-criu-enabled="${target === true}" data-environment="${escapeHTML(row.environment_id)}" data-env-focus="${escapeHTML(row.environment_id + ':criu')}" ${disabled ? 'disabled' : ''}><span></span></button></section>`;
}

/** 在明确点击后读取CAS并应用账号选择。@param {HTMLButtonElement} button 操作按钮。@return {Promise<void>} 实际提交及刷新。 */
async function applyEnvironmentCriu(button) {
  const ui = state.environmentUI, id = button.dataset.environment, generation = state.viewGeneration;
  if (!id || ui.pending.has(id)) return;
  const enabled = button.dataset.criuEnabled === 'true';
  const row = ui.rows.find(value => value.environment_id === id);
  if (!row) return;
  ui.pending.add(id); paintEnvironments();
  try {
    const before = await API(`/environments/${encodeURIComponent(id)}/criu`);
    if (generation !== state.viewGeneration || currentTab() !== 'environments') return;
    if (!await confirmRuntimeAction(`为 ${row.name} ${enabled ? '开启' : '关闭'}CRIU加速？将在空闲时重建环境，保留HOME与账号身份。`)) return;
    await API(`/environments/${encodeURIComponent(id)}/criu`, {method: 'POST', body: JSON.stringify({
      enabled, expected_generation: before.generation, expected_revision: before.revision,
    })});
    if (generation === state.viewGeneration) ui.feedback.set(id, 'CRIU选择已应用，实际恢复状态随巡检更新。');
  } catch (error) {
    if (generation === state.viewGeneration) ui.feedback.set(id, 'CRIU切换失败：' + error.message + '。请刷新实际状态后再操作。');
  } finally {
    ui.pending.delete(id);
    if (generation === state.viewGeneration && currentTab() === 'environments') await renderEnvironments();
  }
}

/**
 * 渲染服务器提供的内核版本、进度和在线管理能力。
 * @param {object} row 含 native_kernel 的环境摘要。
 * @return {string} 内核管理面板。
 */
function renderNativeKernel(row) {
  if (row.native_kernels) return ['2.1.280', '2.1.293'].map(version => renderNativeKernelVersion(row, version, row.native_kernels[version])).join('');
  return renderNativeKernelVersion(row, '2.1.293', row.native_kernel);
}

/** 渲染单版内核管理，动作固定归属于对应源版本。
 * @param {object} row 当前环境。
 * @param {string} sourceVersion 固定280或293。
 * @param {object|null} kernel 对应版本状态。
 * @return {string} 安全转义的管理面板。
 */
function renderNativeKernelVersion(row, sourceVersion, kernel) {
  const id = row.environment_id, key = sourceVersion === '2.1.293' ? id : id + ':280';
  if (!kernel && nativeRuntimePending(row)) return `<section class="env-kernel env-kernel-unavailable"><h4>请求内核 · ${sourceVersion}</h4><p>已选择原生运行时，等待环境准备。</p></section>`;
  if (!kernel) return `<section class="env-kernel env-kernel-unavailable"><h4>请求内核 · ${sourceVersion}</h4><p>此环境当前未提供在线内核管理。</p></section>`;
  const busy = kernelStates(row).some(value => KERNEL_BUSY_STATES.includes(value)) || state.environmentUI.pending.has(id);
  const available = !busy && !row.busy && Object.hasOwn(KERNEL_STATES, kernel.state) && !kernelStates(row).includes('reconcile');
  const version = reference => escapeHTML(reference?.release || '无');
  const discovery = state.environmentUI.kernelReleases?.get(key), checking = state.environmentUI.checkingReleases?.has(key);
  const currentNumber = kernel.current?.release?.match(/^v0\.1\.0-beta\.([1-9][0-9]{0,8})$/)?.[1];
  const latestNumber = discovery?.latest?.match(/^v0\.1\.0-beta\.([1-9][0-9]{0,8})$/)?.[1];
  const newer = currentNumber && latestNumber && Number(latestNumber) > Number(currentNumber);
  const discoveryText = discovery?.state === 'stale' ? '版本检查失败，显示上次发现结果。准备时将重新验签。'
    : discovery?.state === 'unavailable' ? '版本列表暂不可用，当前内核运行保持原状态。'
    : discovery?.state === 'ready' ? (discovery.latest ? `${newer ? '发现新版' : '最新发现版本'}：${discovery.latest}` : '当前发行源暂无配套版本') : '可检查已发布的配套内核版本';
  const button = (operation, label, enabled, digest = '') => `<button type="button" class="btn btn-sm ${operation === 'activate' ? 'btn-primary' : ''}" data-kernel-action="${operation}" data-kernel-source-version="${sourceVersion}" data-environment="${escapeHTML(id)}" data-kernel-revision="${escapeHTML(kernel.revision)}" data-kernel-release="${escapeHTML(kernel.prepared?.release || '')}" data-kernel-digest="${escapeHTML(digest)}" data-env-focus="${escapeHTML(key + ':' + operation)}" ${enabled ? '' : 'disabled'}>${label}</button>`;
  return `<section class="env-kernel"><div class="env-section-head"><h4>请求内核 · ${sourceVersion}</h4><span class="env-tag">在线内核管理</span></div>
    <div class="env-kernel-version"><strong>${version(kernel.current)}</strong><span role="status">${escapeHTML(KERNEL_STATES[kernel.state] || '状态待核对')}</span></div>
    <div class="env-versions"><div><span>已准备候选</span><strong>${version(kernel.prepared)}</strong></div><div><span>上一版本</span><strong>${version(kernel.previous)}</strong></div></div>
    <p class="env-muted" role="status">${escapeHTML(discoveryText)} · 镜像内置 ${version(kernel.builtin)}</p>
    ${kernel.error ? `<p class="env-error" role="alert">${escapeHTML(kernel.error)}</p>` : ''}
    ${row.busy ? '<p class="env-muted">CLI 作业执行中，请在空闲后操作内核。</p>' : ''}
    <div class="env-actions"><button type="button" class="btn btn-sm" data-kernel-check data-kernel-source-version="${sourceVersion}" data-environment="${escapeHTML(id)}" data-env-focus="${escapeHTML(key + ':updates')}" ${busy || checking ? 'disabled' : ''}>${checking ? '检查中…' : '检查更新'}</button>${button('prepare', '选择版本', available)}${button('activate', '激活候选', available && kernel.prepared && kernel.prepared.launcher_sha256 !== kernel.current?.launcher_sha256, kernel.prepared?.launcher_sha256)}${button('rollback', '回滚内核', available && kernel.previous, kernel.previous?.launcher_sha256)}${kernel.state === 'reconcile' ? button('recover', '恢复对账', !busy && !row.busy) : ''}</div>
    <details class="env-kernel-details" data-env-details="${escapeHTML(key + ':kernel')}"><summary>版本摘要与预热回执</summary><dl><dt>当前分发 SHA256</dt><dd><code>${escapeHTML(kernel.current?.launcher_sha256 || '未提供')}</code></dd><dt>候选分发 SHA256</dt><dd><code>${escapeHTML(kernel.prepared?.launcher_sha256 || '未准备')}</code></dd><dt>上一版分发 SHA256</dt><dd><code>${escapeHTML(kernel.previous?.launcher_sha256 || '无')}</code></dd><dt>上次预热回执 PID</dt><dd>${escapeHTML(kernel.pid ?? '未采集')}</dd><dt>实际映像 SHA256</dt><dd><code>${escapeHTML(kernel.image_sha256 || '未采集')}</code></dd></dl></details>
  </section>`;
}

/**
 * 分派明确点击的内核、实测、时段或维护操作。
 * @param {HTMLButtonElement} button 当前卡片的操作按钮。
 * @return {Promise<void>} 当前动作及状态刷新完成。
 */
async function handleEnvironmentAction(button) {
  if (button.dataset.envOpen) return openEnvironmentWorkspace(button);
  const ui = state.environmentUI, id = button.dataset.environment, generation = state.viewGeneration;
  if (!id || ui.pending.has(id)) return;
  if (button.hasAttribute('data-native-prepare')) return retryNativePreparation(button);
  if (button.dataset.kernelAction) return openNativeKernelDialog(button);
  if (button.hasAttribute('data-kernel-check')) return checkKernelUpdates(button);
  if (button.hasAttribute('data-criu-enabled')) return applyEnvironmentCriu(button);
  if (button.hasAttribute('data-cpu-resources')) return openCpuResourceDialog(button);
  if (button.hasAttribute('data-content-capture')) return openContentCaptureDialog(button);
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
  if (!physical && !await confirmRuntimeAction(operation === 'reprofile' ? '画像校正会生成新的环境参数，并保留登录凭据。确认继续？' : '确认在账号空闲时执行此维护操作？持久数据会保留。')) return;
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

/** 只读检查发行列表，迟到回包按页面代次丢弃。@param {HTMLButtonElement} button 检查按钮。@return {Promise<void>} 发现结果与页面刷新。 */
async function checkKernelUpdates(button) {
  const ui = state.environmentUI, id = button.dataset.environment, generation = state.viewGeneration;
  const sourceVersion = button.dataset.kernelSourceVersion || '2.1.293';
  const key = sourceVersion === '2.1.293' ? id : id + ':280';
  if (!id || !['2.1.280', '2.1.293'].includes(sourceVersion) || ui.checkingReleases.has(key)) return;
  ui.checkingReleases.add(key); paintEnvironments();
  try {
    const value = await API(`/environments/${encodeURIComponent(id)}/native-kernel/releases?refresh=true&source_version=${sourceVersion}`);
    if (generation === state.viewGeneration && currentTab() === 'environments') ui.kernelReleases.set(key, value);
  } catch (error) {
    if (generation === state.viewGeneration) ui.feedback.set(id, '检查内核更新失败：' + error.message);
  } finally {
    ui.checkingReleases.delete(key);
    if (generation === state.viewGeneration && currentTab() === 'environments') paintEnvironments();
  }
}

/**
 * 打开内核操作窗口，冻结用户看到的版本和前置状态。
 * @param {HTMLButtonElement} button 已显示的内核动作。
 * @return {Promise<void>} 窗口与已发布版本列表加载完成。
 */
async function openNativeKernelDialog(button) {
  if (state.kernelDialog) return;
  const id = button.dataset.environment;
  const row = state.environmentUI.rows.find(item => item.environment_id === id);
  const operation = button.dataset.kernelAction;
  const sourceVersion = button.dataset.kernelSourceVersion || '2.1.293';
  if (!row || !['2.1.280', '2.1.293'].includes(sourceVersion) || !['prepare', 'activate', 'rollback', 'recover'].includes(operation)) return;
  const labels = {prepare: '准备内核', activate: '激活候选', rollback: '回滚内核', recover: '恢复对账'};
  const kernel = row.native_kernels?.[sourceVersion] || (sourceVersion === '2.1.293' ? row.native_kernel : null);
  if (!kernel) return;
  const target = operation === 'activate' ? kernel.prepared : operation === 'rollback' ? kernel.previous : null;
  const request = {id, operation, sourceVersion, revision: button.dataset.kernelRevision, digest: button.dataset.kernelDigest || null,
    release: operation === 'activate' ? button.dataset.kernelRelease : null, generation: state.viewGeneration,
    focus: button.dataset.envFocus, sending: false, loading: operation === 'prepare', versions: []};
  state.kernelDialog = request;
  const form = $('#native-kernel-form'), modal = $('#native-kernel-modal');
  form.reset();
  form.elements.release.disabled = operation !== 'prepare';
  $('#native-kernel-release-field').classList.toggle('hidden', operation !== 'prepare');
  $('#native-kernel-title').textContent = labels[operation];
  $('#native-kernel-account').textContent = row.name + ' · ' + sourceVersion;
  $('#native-kernel-current').textContent = kernel.current?.release || '待核对';
  $('#native-kernel-target').textContent = operation === 'prepare' ? '选择已发布版本后下载并验签' : target?.release || '按服务器持久状态恢复';
  $('#native-kernel-description').textContent = operation === 'prepare'
    ? '准备期间当前内核继续接单。准备完成后可单独激活候选。'
    : '将等待该账号在途请求结束，完成目标内核的预热与身份核验后继续接单。';
  $('#native-kernel-feedback').textContent = '';
  const submit = $('button[type="submit"]', form);
  submit.textContent = labels[operation];
  submit.disabled = request.loading;
  form.onsubmit = submitNativeKernel;
  modal.onkeydown = event => {
    if (event.key !== 'Tab') return;
    const nodes = $$('button:not(:disabled), input:not(:disabled), select:not(:disabled)', modal).filter(node => node.getClientRects().length);
    const index = nodes.indexOf(document.activeElement);
    if (event.shiftKey && index <= 0) { event.preventDefault(); nodes.at(-1)?.focus(); }
    else if (!event.shiftKey && index === nodes.length - 1) { event.preventDefault(); nodes[0]?.focus(); }
  };
  openModal('#native-kernel-modal');
  (operation === 'prepare' ? form.elements.release : $('button[type="submit"]', form)).focus();
  if (operation === 'prepare') {
    form.elements.release.replaceChildren(new Option('正在读取已发布版本…', ''));
    form.elements.release.disabled = true;
    try {
      const value = await API(`/environments/${encodeURIComponent(id)}/native-kernel/releases?source_version=${sourceVersion}`);
      if (state.kernelDialog !== request || request.generation !== state.viewGeneration) return;
      state.environmentUI.kernelReleases.set(sourceVersion === '2.1.293' ? id : id + ':280', value);
      const versions = Array.isArray(value.versions) ? value.versions.filter(item => typeof item?.release === 'string' && /^v0\.1\.0-beta\.[1-9][0-9]{0,8}$/.test(item.release)) : [];
      request.versions = versions.map(item => item.release);
      form.elements.release.replaceChildren(...versions.map(item => new Option(item.release, item.release)));
      request.loading = false;
      form.elements.release.disabled = !versions.length;
      submit.disabled = !versions.length;
      $('#native-kernel-feedback').textContent = !versions.length ? '暂无可选择版本，请关闭窗口后检查更新。'
        : value.state === 'stale' ? '显示上次发现的版本。准备时仍会校验签名和精确摘要。' : '';
      if (versions.length) form.elements.release.focus();
    } catch (error) {
      if (state.kernelDialog === request) {
        request.failed = true;
        $('#native-kernel-feedback').textContent = '读取版本失败：' + error.message + '。请关闭窗口后重新检查。';
      }
    }
  }
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
  if (!request || request.sending || request.loading || request.failed || request.generation !== state.viewGeneration) return;
  const release = request.operation === 'prepare' ? form.elements.release.value.trim() : request.release;
  if (request.operation === 'prepare' && !request.versions.includes(release)) return;
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
      operation: request.operation, source_version: request.sourceVersion, operation_id, release, expected_sha256: request.digest, expected_revision: request.revision
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


/** 打开独立CPU表单，列表轮询保持当前输入。
 * @param {HTMLButtonElement} button 本环境资源入口。
 * @return {Promise<void>} 读取当前实际额度完成。
 */
async function openCpuResourceDialog(button) {
  if (state.cpuDialog) return;
  const id = button.dataset.environment, row = state.environmentUI.rows.find(item => item.environment_id === id);
  if (!row) return;
  const request = {id, generation: state.viewGeneration, focus: button.dataset.envFocus, sending: false, resources: null, inline: !!environmentWorkspace && environmentWorkspace.id===id && environmentWorkspace.tab==='resources'};
  state.cpuDialog = request;
  const modal = $('#cpu-resource-modal'), form = $('#cpu-resource-form');
  $('#cpu-resource-description').textContent = `${row.name || '当前环境'} · 正在读取实际额度`;
  $('#cpu-resource-feedback').textContent = '';
  $$('input, button[type="submit"]', form).forEach(node => { node.disabled = true; if (node.tagName === 'INPUT') node.value = ''; });
  form.onsubmit = submitCpuResources;
  modal.onkeydown = event => {
    if (event.key !== 'Tab') return;
    const nodes = $$('button:not(:disabled), input:not(:disabled)', modal).filter(node => node.getClientRects().length);
    const index = nodes.indexOf(document.activeElement);
    if (event.shiftKey && index <= 0) { event.preventDefault(); nodes.at(-1)?.focus(); }
    else if (!event.shiftKey && index === nodes.length - 1) { event.preventDefault(); nodes[0]?.focus(); }
  };
  if(request.inline){$('#environment-resource-editor').append(form);form.closest('.environment-cpu-section').classList.add('editing');}
  else {openModal('#cpu-resource-modal');$('[data-close]', modal).focus();}
  try {
    const resources = await API(`/environments/${encodeURIComponent(id)}/cpu-resources`);
    if (state.cpuDialog !== request) return;
    request.resources = resources;
    (state.environmentUI.cpuSnapshots ||= new Map()).set(id, resources);
    $('#cpu-resource-description').textContent = `${row.name || '当前环境'} · 宿主 ${resources.host_cpus} 核 · 代次 ${resources.generation}`;
    for (const role of ['cli', 'sender', 'network']) {
      form.elements[role].value = resources.cpus[role];
      form.elements[role].max = resources.host_cpus;
      form.elements[role].disabled = false;
    }
    $('button[type="submit"]', form).disabled = false;
  } catch (error) {
    if (state.cpuDialog === request) $('#cpu-resource-feedback').textContent = '读取失败：' + error.message;
  }
}

/** 关闭CPU窗口并使迟到回执失效。
 * @param {boolean} force 导航离页时强制收口窗口。
 * @return {boolean} 是否完成关闭。
 */
function closeCpuResourceDialog(force = false) {
  const request = state.cpuDialog, modal = $('#cpu-resource-modal');
  if (!modal || (request?.sending && !force)) return false;
  state.cpuDialog = null;
  if(request?.inline){$('.modal-card',modal).append($('#cpu-resource-form'));$('#environment-workspace-body .environment-cpu-section')?.classList.remove('editing');}
  modal.classList.add('hidden');
  modal.onkeydown = null;
  $$('[data-close]', modal).forEach(button => { button.disabled = false; });
  if (request && !force) {
    const trigger = $$('[data-env-focus]').find(node => node.dataset.envFocus === request.focus && !node.disabled);
    (trigger || $('#environment-refresh'))?.focus({preventScroll: true});
  }
  return true;
}

/** 提交用户已看到的实际版本，失败时要求重新读取，避免覆盖并发设置。
 * @param {SubmitEvent} event 表单提交事件。
 * @return {Promise<void>} 保存及当前页面刷新完成。
 */
async function submitCpuResources(event) {
  event.preventDefault();
  const request = state.cpuDialog;
  if (!request?.resources || request.sending) return;
  const modal = $('#cpu-resource-modal'), form = $('#cpu-resource-form');
  const cpus = Object.fromEntries(['cli', 'sender', 'network'].map(role => [role, Number(form.elements[role].value)]));
  request.sending = true;
  $$('input, button', request.inline ? form : modal).forEach(node => { node.disabled = true; });
  $('#cpu-resource-feedback').textContent = '正在应用并核对实际额度…';
  try {
    const result=await API(`/environments/${encodeURIComponent(request.id)}/cpu-resources`, {method: 'POST', body: JSON.stringify({
      expected_generation: request.resources.generation, expected_revision: request.resources.revision, cpus
    })});
    if (state.cpuDialog !== request) return;
    request.sending = false;
    if(request.inline){
      request.resources=result;(state.environmentUI.cpuSnapshots ||= new Map()).set(request.id,result);
      $$('input,button',form).forEach(node=>{node.disabled=false;});
      for(const role of ['cli','sender','network'])form.elements[role].value=result.cpus[role];
      $('#cpu-resource-feedback').textContent='CPU 额度已应用，重建配置已保存。';
    }else closeCpuResourceDialog();
    state.environmentUI.feedback.set(request.id, 'CPU 额度已应用，重建配置已保存。');
  } catch (error) {
    if (state.cpuDialog === request) $('#cpu-resource-feedback').textContent = '保存失败：' + error.message + '。请关闭窗口并重新读取实际额度。';
  } finally {
    request.sending = false;
    if (state.cpuDialog === request) $$('[data-close]', request.inline?form:modal).forEach(button => { button.disabled = false; });
    if (request.generation === state.viewGeneration && currentTab() === 'environments') await renderEnvironments();
  }
}

/** 打开采集切换窗口并冻结实际版本。@param {HTMLButtonElement} button 账号开关。@return {Promise<void>} 读取结束。 */
async function openContentCaptureDialog(button) {
  if (state.captureDialog) return;
  const row = state.environmentUI.rows.find(item => item.environment_id === button.dataset.environment);
  if (!row) return;
  const request = {id: row.environment_id, generation: state.viewGeneration, focus: button.dataset.envFocus,
    sending: false, settings: null};
  state.captureDialog = request;
  const modal = $('#content-capture-modal'), form = $('#content-capture-form');
  $('#content-capture-description').textContent = `${row.name} · 正在读取实际采集配置`;
  $('#content-capture-feedback').textContent = '';
  $('button[type="submit"]', form).disabled = true;
  form.onsubmit = submitContentCapture;
  modal.onkeydown = event => {
    if (event.key !== 'Tab') return;
    const nodes = $$('button:not(:disabled)', modal).filter(node => node.getClientRects().length);
    const index = nodes.indexOf(document.activeElement);
    if (event.shiftKey && index <= 0) { event.preventDefault(); nodes.at(-1)?.focus(); }
    else if (!event.shiftKey && index === nodes.length - 1) { event.preventDefault(); nodes[0]?.focus(); }
  };
  openModal('#content-capture-modal');
  $('[data-close]', modal).focus();
  try {
    const settings = await API(`/environments/${encodeURIComponent(request.id)}/content-capture`);
    if (state.captureDialog !== request) return;
    request.settings = settings;
    $('#content-capture-description').textContent = `${row.name} · ${settings.enabled ? '已开启 → 关闭' : '已关闭 → 开启'} · 环境代次 ${settings.generation}`;
    $('button[type="submit"]', form).disabled = !settings.supported || !settings.applied;
    if (!settings.supported || !settings.applied) $('#content-capture-feedback').textContent = '原生发送器配置待核对，请先处理环境维护状态。';
  } catch (error) {
    if (state.captureDialog === request) $('#content-capture-feedback').textContent = '读取失败：' + error.message;
  }
}

/** 显示同代次TLS能力，完整性由单次请求记录说明。@param {object} value 服务端状态。@return {string} 安全文字。 */
function tlsCaptureDescription(value) {
  const names = {not_installed: '需系统更新安装采集器', disabled: '已关闭', stopped: '停止待启动', preparing: '准备中', ready: '已就绪', unavailable: '暂不可用'};
  const reasons = {OBSERVER_NOT_CONFIGURED: '采集器尚未安装', OBSERVER_STATUS_STALE: '检查结果已过期',
    OBSERVER_STATUS_UNAVAILABLE: '等待实际检查', IMAGE_NOT_ADMITTED: '当前内核尚未准入',
    PROBE_ATTACH_FAILED: '探针附着失败', BPF_LOAD_FAILED: '探针加载失败',
    OBSERVER_FAILED: '采集器已退出', CAPTURE_PREPARING: '后台准备中'};
  const name = names[value?.state] || '状态待检查';
  const reason = value?.reason && value.state !== 'preparing' ? (reasons[value.reason] || value.reason) : '';
  return `原生 TLS 采集：${name}${reason ? ' · ' + reason : ''}`;
}

/** 统一关闭采集窗口并作废旧回执。@param {boolean} force 离页强制关闭。@return {boolean} 是否关闭。 */
function closeContentCaptureDialog(force = false) {
  const request = state.captureDialog, modal = $('#content-capture-modal');
  if (!modal || (request?.sending && !force)) return false;
  state.captureDialog = null;
  modal.classList.add('hidden'); modal.onkeydown = null;
  $$('[data-close]', modal).forEach(button => { button.disabled = false; });
  if (request && !force) {
    ($$('[data-env-focus]').find(node => node.dataset.envFocus === request.focus && !node.disabled)
      || $('#environment-refresh'))?.focus({preventScroll: true});
  }
  return true;
}

/** 提交一次冻结的采集切换，失败后要求重新读取。@param {SubmitEvent} event 表单事件。@return {Promise<void>} 应用及刷新结束。 */
async function submitContentCapture(event) {
  event.preventDefault();
  const request = state.captureDialog;
  if (!request?.settings || request.sending) return;
  request.sending = true;
  const modal = $('#content-capture-modal');
  $$('button', modal).forEach(button => { button.disabled = true; });
  $('#content-capture-feedback').textContent = '正在等待空闲门禁并核对发送器配置…';
  try {
    const result = await API(`/environments/${encodeURIComponent(request.id)}/content-capture`, {method: 'POST', body: JSON.stringify({
      enabled: !request.settings.enabled, expected_generation: request.settings.generation,
      expected_revision: request.settings.revision
    })});
    if (state.captureDialog !== request) return;
    request.sending = false;
    closeContentCaptureDialog();
    state.environmentUI.feedback.set(request.id, `请求内容采集已${result.enabled ? '开启' : '关闭'}，对后续请求生效。`);
  } catch (error) {
    if (state.captureDialog === request) $('#content-capture-feedback').textContent = '切换失败：' + error.message + '。请关闭窗口并重新读取。';
  } finally {
    request.sending = false;
    if (state.captureDialog === request) $$('[data-close]', modal).forEach(button => { button.disabled = false; });
    if (request.generation === state.viewGeneration && currentTab() === 'environments') await renderEnvironments();
  }
}
