/** 新 Projects：围绕账号 Pi、真实终端与工作记录组织界面。 */
window.ProjectsUI = (() => {
  let api, prefix, source, accountId = null, agents = [], catalog = [], accounts = [], cursor = 0;
  let revision = 0, selection = 0, scheduleClock = null, recordPages = {};
  let screenWorkId = null, screenEventId = 0;
  const pendingActions = new Map();
  const $ = selector => document.querySelector(selector);
  const escape = value => String(value ?? '').replace(/[&<>"']/g, character =>
    ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[character]));
  const names = {off: '未启动', running: 'Pi 指挥中', waiting: '等待执行条件', paused: '已暂停',
    blocked: '需要处理', ready: '待开始', verifying: '独立验收中', passed: '验收通过', stopped: '已停止'};

  /**
   * 在当前页面显示操作结果，页面切换后不再写入旧 DOM。
   * @param {string} message 用户可读消息。
   * @param {string} kind 错误告警或普通状态。
   * @return {void}
   */
  function feedback(message, kind = 'status') {
    const element = $('#projects-feedback');
    if (!element) return;
    element.dataset.kind = kind;
    element.setAttribute('role', kind === 'error' ? 'alert' : 'status');
    element.setAttribute('aria-live', kind === 'error' ? 'assertive' : 'polite');
    element.textContent = message; element.classList.toggle('hidden', !message);
  }

  /**
   * 统一处理按钮操作及错误。
   * @param {Function} action 异步操作。
   * @return {Promise<void>} 操作完成。
   */
  async function perform(action) {
    try { feedback(''); await action(); } catch (error) { feedback(error.message); }
  }

  /**
   * 进入账号控制页，旧连接和旧回调均在退出后失效。
   * @param {object} options 既有鉴权 API 与路径前缀。
   * @return {Promise<void>} 初始页面加载完成。
   */
  async function mount(options) {
    unmount();
    const current = revision;
    api = options.api; prefix = options.prefix;
    $('#projects-agent-form').onsubmit = event => { event.preventDefault(); perform(saveAgent); };
    $('#projects-schedule-form').onsubmit = event => { event.preventDefault(); perform(saveSchedule); };
    $('#projects-model-form').onsubmit = event => { event.preventDefault(); perform(saveModel); };
    $('#projects-model-reset').onclick = () => perform(async () => {
      await api('/settings/project-requester', {method: 'DELETE'}); await loadModel();
    });
    $('#projects-filter').oninput = paintCatalog;
    $('#projects-select-all').onclick = () => paintCatalog(catalog.map(item => item.project_key));
    $('#projects-clear-all').onclick = () => paintCatalog([]);
    $('#projects-projects').onchange = paintSelectionCount;
    $('#projects-account').onchange = event => selectAccount(Number(event.target.value));
    fillSchedule();
    scheduleClock = setInterval(paintSchedule, 1000);
    $('#projects-tab-terminal').onclick = () => selectTab('terminal');
    $('#projects-tab-events').onclick = () => selectTab('events');
    for (const kind of ['events', 'history']) {
      for (const direction of ['previous', 'next', 'latest']) {
        $(`#projects-${kind}-${direction}`).onclick = () => perform(() => loadPage(kind, direction));
      }
      $(`#projects-${kind}-new`).onclick = () => perform(() => loadPage(kind, 'latest'));
    }
    document.querySelectorAll('[data-pi-action]').forEach(button => {
      button.onclick = () => runAction(button.dataset.piAction);
    });
    try {
      const values = await Promise.all([api('/projects'), api('/projects/catalog'), api('/accounts')]);
      if (current !== revision) return;
      agents = values[0].agents; catalog = values[1].projects; accounts = values[2];
      $('#projects-runtime').textContent = values[0].pi_available ? 'Pi 运行时已就绪' : '当前镜像尚未包含 Pi 运行时';
      $('#projects-research-count').textContent = `${catalog.length} 个研究项目 · ${catalog.filter(item => item.ready).length} 个具备工程验收`;
      const usable = accounts.filter(item => item.enabled && !item.deleted_at);
      $('#projects-account').innerHTML = '<option value="">选择运行账号</option>' + usable.map(item =>
        `<option value="${item.id}">${escape(item.name)}</option>`).join('');
      paintCatalog();
      await loadModel();
      const first = agents.find(item => usable.some(account => account.id === item.account_id));
      if (first) { $('#projects-account').value = first.account_id; await selectAccount(first.account_id); }
    } catch (error) { if (current === revision) feedback(error.message); }
  }

  /**
   * 关闭事件连接，使切页前的异步响应失效。
   * @return {void}
   */
  function unmount() {
    revision += 1;
    selection += 1;
    source?.close(); source = null;
    clearInterval(scheduleClock); scheduleClock = null;
    pendingActions.clear();
    cursor = 0; accountId = null; screenWorkId = null; screenEventId = 0;
    resetRecords();
  }

  /**
   * 为当前账号独立保存已读分页，浏览旧页时暂存新记录。
   * @return {void}
   */
  function resetRecords() {
    recordPages = Object.fromEntries([['events', 20], ['history', 10]].map(([kind, size]) =>
      [kind, {size, pages: [], index: 0, loading: false, pending: new Set(), incoming: []}]));
  }

  /**
   * 更新当前账号摘要，保持表单编辑及目录滚动位置。
   * @param {object} value 后端控制摘要。
   * @return {void}
   */
  function updateAgents(value) {
    for (const agent of value.agents) {
      const index = agents.findIndex(item => item.account_id === agent.account_id);
      // 操作回执只含核心状态；保留最近 GET/SSE 提供的额度、进度和活动，直到新的视图明确更新它们。
      if (index < 0) agents.push(agent); else agents[index] = {...agents[index], ...agent};
    }
  }

  /**
   * 切换执行现场标签，终端和交互列表各自保留滚动位置。
   * @param {string} name 终端或交互标签。
   * @return {void}
   */
  function selectTab(name) {
    for (const tab of ['terminal', 'events']) {
      $(`#projects-tab-${tab}`).setAttribute('aria-selected', String(tab === name));
      $(`#projects-${tab}-panel`).classList.toggle('hidden', tab !== name);
    }
  }

  /**
   * 刷新公开运行视图，保持所有尚未保存的配置输入。
   * @return {Promise<void>} 摘要已更新。
   */
  async function refreshView() {
    const current = revision, selected = accountId;
    const value = await api('/projects');
    if (current !== revision || selected !== accountId) return;
    updateAgents(value); paintState();
  }

  /**
   * 立即反馈正在进行的控制操作，同一账号请求完成前不能重复点击。
   * @param {string} action 启动、暂停或停止。
   * @return {Promise<void>} 控制回执及公开视图已读取。
   */
  async function runAction(action) {
    if (!accountId) { feedback('请先选择并保存账号项目池'); return; }
    const selected = accountId, current = revision, chosen = selection;
    if (pendingActions.has(selected)) return;
    const pending = {action};
    pendingActions.set(selected, pending); paintState();
    feedback(action === 'start' ? '正在启动 / 恢复 Pi，核对账号与执行条件…'
      : action === 'pause' ? '正在暂停 Pi 并关闭自动计划，保留原会话…' : '正在停止当前目标并保留现场…');
    try {
      const result = await api(`/projects/agents/${selected}/${action}`, {method: 'POST'});
      if (current !== revision || selected !== accountId || chosen !== selection) return;
      updateAgents(result); paintState(); await loadReconciliation();
      const agent = agents.find(item => item.account_id === selected);
      feedback(action === 'start' ? agent?.controller_active ? 'Pi 已启动，正在读取项目和原会话。'
        : agent?.message || '执行条件尚未满足，请查看运行总览。'
        : action === 'pause' ? '已暂停，自动计划已关闭，原会话和工作区已保留。' : '当前目标已停止，现场和交付记录已保留。');
      await refreshView();
    } catch (error) {
      if (current === revision && selected === accountId && chosen === selection)
        feedback(`${action === 'start' ? '启动 / 恢复' : action === 'pause' ? '暂停' : '停止'}未完成：${error.message}`, 'error');
    } finally {
      if (pendingActions.get(selected) === pending) pendingActions.delete(selected);
      if (current === revision && selected === accountId && chosen === selection) paintState();
    }
  }

  /**
   * 切换账号时恢复其项目池，并建立仅属于该账号的事件连接。
   * @param {number} id 账号 ID。
   * @return {Promise<void>} 账号历史加载完成。
   */
  async function selectAccount(id) {
    const request = ++selection;
    source?.close(); source = null;
    accountId = id || null; cursor = 0; resetRecords();
    screenWorkId = null; screenEventId = 0;
    const agent = agents.find(item => item.account_id === accountId);
    const form = $('#projects-agent-form');
    form.elements.instructions.value = agent?.instructions || '';
    form.elements.budget_minutes.value = (agent?.budget_sec || 3600) / 60;
    fillSchedule();
    paintCatalog(agent?.project_keys || []); paintState(); paintRecords('events'); paintRecords('history');
    paintScreen();
    if (!accountId) return;
    const selected = accountId, current = revision;
    try {
      const [snapshot, history] = await Promise.all([api(`/projects/agents/${selected}/snapshot`),
        api(`/projects/agents/${selected}/work/page?limit=10`), loadReconciliation()]);
      if (current !== revision || selected !== accountId || request !== selection) return;
      updateAgents(snapshot.state); cursor = snapshot.cursor;
      recordPages.events.pages = [snapshot.events]; recordPages.history.pages = [history];
      paintState(); paintRecords('events'); paintRecords('history');
      paintScreen(snapshot.observation);
      source = new EventSource(`${prefix}/api/projects/stream?account_id=${selected}&after=${cursor}`);
      source.addEventListener('update', event => {
        if (current !== revision || selected !== accountId || request !== selection) return;
        try {
          const payload = JSON.parse(event.data);
          updateAgents(payload.state);
          paintScreen();
          const observations = [], interactions = [];
          for (const item of payload.events) {
            if (item.id <= cursor) continue;
            cursor = item.id;
            if (item.kind === 'observation') observations.push(item);
            else if (item.kind !== 'usage') interactions.push(item);
          }
          receiveRecords('events', interactions);
          paintScreen(observations.reverse().find(item => item.work_id === screenWorkId));
          const work = agents.find(item => item.account_id === accountId)?.work;
          if (work) receiveRecords('history', [work]);
          paintState();
          if (payload.events.some(item => ['input_unknown', 'reconciled'].includes(item.kind))) {
            loadReconciliation().catch(error => feedback(error.message));
          }
        } catch { feedback('Pi 事件流暂不可用，请刷新核对状态'); }
      });
      source.onerror = () => {
        if (current === revision && selected === accountId && request === selection)
          feedback('连接中断，正在重新连接；Claude 会话仍保留。');
      };
    } catch (error) {
      if (current === revision && selected === accountId && request === selection) feedback(error.message, 'error');
    }
  }

  /**
   * 筛选项目时保留已勾选的项目，不改变用户的授权池。
   * @param {Array<string>|undefined} selected 明确切换账号时的选中列表。
   * @return {void}
   */
  function paintCatalog(selected) {
    if (!Array.isArray(selected)) selected = Array.from(document.querySelectorAll('[name=project_key]:checked')).map(item => item.value);
    const query = $('#projects-filter').value.trim().toLowerCase();
    $('#projects-projects').innerHTML = catalog.map(item => {
      const visible = `${item.project_key} ${item.title}`.toLowerCase().includes(query);
      return `<div class="projects-choice${visible ? '' : ' hidden'}"><label><input type="checkbox" name="project_key" value="${escape(item.project_key)}"${selected.includes(item.project_key) ? ' checked' : ''}>
        <span><strong>${escape(item.project_key)}</strong><small class="muted">${item.ready ? `${item.objectives.length} 项工程目标` : '研究资料'}</small></span></label>
        <button type="button" class="btn btn-sm" data-research="${escape(item.project_key)}">研究</button></div>`;
    }).join('') || '<p class="hint">暂无项目研究资料。</p>';
    paintSelectionCount();
    document.querySelectorAll('[data-research]').forEach(button => {
      button.onclick = () => perform(async () => {
        const selectedRevision = revision;
        const project = await api('/projects/catalog/' + encodeURIComponent(button.dataset.research));
        if (selectedRevision !== revision) return;
        $('#projects-research-title').textContent = project.title;
        $('#projects-research-body').textContent = [project.research.report, project.research.roadmap,
          ...project.objectives.map(item => `${item.goal}\n\n${item.prompt}`)].filter(Boolean).join('\n\n');
        $('#projects-research').open = true;
      });
    });
  }

  /**
   * 汇总完整授权池，单项勾选时保留当前焦点和滚动位置。
   * @return {void}
   */
  function paintSelectionCount() {
    const keys = new Set(Array.from(document.querySelectorAll('[name=project_key]:checked')).map(item => item.value));
    const executable = catalog.filter(item => keys.has(item.project_key) && item.ready).length;
    $('#projects-selected-count').textContent = `已选 ${keys.size} 个 · ${executable} 个可执行`;
  }

  /**
   * 保存账号项目池，保存本身不启动真实模型。
   * @return {Promise<void>} 配置已保存。
   */
  async function saveAgent() {
    if (!accountId) throw new Error('请先选择运行账号');
    const form = $('#projects-agent-form');
    const keys = Array.from(document.querySelectorAll('[name=project_key]:checked')).map(item => item.value);
    const value = await api(`/projects/agents/${accountId}`, {method: 'PUT', body: JSON.stringify({
      project_keys: keys, instructions: form.elements.instructions.value,
      budget_sec: Number(form.elements.budget_minutes.value) * 60,
    })});
    updateAgents(value); paintState(); feedback('项目池和指南已保存。');
    $('#projects-schedule-form').querySelectorAll('input, button').forEach(element => { element.disabled = false; });
    if (!source) await selectAccount(accountId);
    await refreshView();
  }

  /**
   * 仅在切换账号或明确保存计划后回填，实时状态不覆盖尚未保存的输入。
   * @return {void}
   */
  function fillSchedule() {
    const agent = agents.find(item => item.account_id === accountId);
    const form = $('#projects-schedule-form');
    form.elements.schedule_enabled.checked = agent?.schedule?.enabled === true;
    form.elements.interval_minutes.value = agent?.schedule?.interval_minutes ?? 60;
    form.querySelectorAll('input, button').forEach(element => { element.disabled = !agent; });
    paintSchedule();
  }

  /**
   * 独立保存定时设置，不暂停或重新创建当前控制者。
   * @return {Promise<void>} 计划已保存并回显。
   */
  async function saveSchedule() {
    if (!accountId) throw new Error('请先选择账号并保存项目池');
    const selected = accountId, current = revision, chosen = selection;
    const form = $('#projects-schedule-form');
    const enabled = form.elements.schedule_enabled.checked;
    const value = await api(`/projects/agents/${selected}/schedule`, {method: 'PUT', body: JSON.stringify({
      enabled, interval_minutes: Number(form.elements.interval_minutes.value),
    })});
    if (current !== revision || selected !== accountId || chosen !== selection) return;
    updateAgents(value); fillSchedule(); paintState();
    feedback(enabled ? '自动计划已保存；满足账号运行条件后继续指挥。' : '自动计划已关闭；当前任务保持原状态。');
    await refreshView();
  }

  /**
   * 显示已保存的自动计划和倒计时，不修改表单编辑值。
   * @return {void}
   */
  function paintSchedule() {
    const status = $('#projects-schedule-status'), next = $('#projects-schedule-next');
    if (!status || !next) return;
    const agent = agents.find(item => item.account_id === accountId);
    if (!agent) {
      status.textContent = '先保存账号项目池，再启用自动指挥。';
      next.textContent = '';
      return;
    }
    const schedule = agent.schedule;
    const states = {off: '未启用', scheduled: '已安排', running: '本轮指挥中', waiting: '等待执行条件',
      blocked: '需要处理', completed: '项目池已完成'};
    status.textContent = schedule?.enabled
      ? `定时已开启 · ${states[schedule.state] || schedule.state} · 每轮结束后间隔 ${schedule.interval_minutes} 分钟`
      : `定时已关闭${agent.controller_active ? ' · 当前 Pi 继续运行' : ''}`;
    if (schedule?.message) status.textContent += `；${schedule.message}`;
    const timestamp = schedule?.next_run_at;
    if (schedule?.enabled && typeof timestamp === 'number' && Number.isFinite(timestamp)) {
      const seconds = Math.max(0, Math.ceil(timestamp - Date.now() / 1000));
      const waiting = seconds ? `约 ${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒后检查` : '已到时间，等待核对执行条件';
      next.textContent = `下次检查：${new Date(timestamp * 1000).toLocaleString('zh-CN', {hour12: false})}（浏览器当地时间）· ${waiting}`;
    } else if (schedule?.enabled) {
      next.textContent = schedule.state === 'blocked' ? '请处理原因后重新保存计划或手动启动。'
        : schedule.state === 'completed' ? '暂无未完成目标，更新项目池后继续。'
        : agent.controller_active ? '当前一轮结束后安排下次检查。' : '等待执行条件变化后再检查。';
    } else {
      next.textContent = agent.controller_active && ['running', 'waiting'].includes(agent.status)
        ? '当前轮次继续运行；结束后等待你手动启动下一轮。' : '自动计划已关闭，由你手动启动或恢复。';
    }
  }

  /**
   * 用真实累计秒数显示工作时间，不推测任务完成百分比。
   * @param {number|null|undefined} seconds 已采集秒数。
   * @return {string} 中文时长或未采集说明。
   */
  function duration(seconds) {
    if (typeof seconds !== 'number' || !Number.isFinite(seconds)) return '未采集';
    const value = Math.max(0, Math.floor(seconds));
    return value >= 3600 ? `${Math.floor(value / 3600)} 小时 ${Math.floor(value % 3600 / 60)} 分`
      : `${Math.floor(value / 60)} 分 ${value % 60} 秒`;
  }

  /**
   * 显示公开被动额度和用户阈值，未知数值始终留空而非冒充零。
   * @param {object|undefined} admission 最近一次公开门禁视图。
   * @return {void}
   */
  function paintQuota(admission) {
    const quota = admission?.quota;
    for (const key of ['five_hour', 'seven_day']) {
      const element = $(`#projects-quota-${key}`), value = quota?.windows?.[key]?.utilization;
      const measured = quota?.known !== false && typeof value === 'number' && Number.isFinite(value) && value >= 0;
      const limit = quota?.limits?.[key], limited = typeof limit === 'number' && Number.isFinite(limit) && limit > 0;
      const fill = element.querySelector('[data-quota-fill]'), marker = element.querySelector('[data-quota-limit]');
      element.querySelector('[data-quota-value]').textContent = measured ? `${Number(value.toFixed(1))}%` : '未采集';
      element.dataset.known = String(measured);
      element.dataset.hit = String((quota?.hit || []).includes(key));
      fill.classList.toggle('hidden', !measured);
      fill.style.width = measured ? `${Math.min(100, value)}%` : '';
      if (measured) fill.setAttribute('aria-valuenow', String(value)); else fill.removeAttribute('aria-valuenow');
      marker.classList.toggle('hidden', !limited);
      marker.style.left = limited ? `${Math.min(100, limit)}%` : '';
      marker.title = limited ? `自动运行阈值 ${limit}%` : '';
      const observed = quota?.observed_at;
      element.querySelector('[data-quota-description]').textContent = `${limited ? `运行阈值 ${limit}%` : '未设置运行阈值'} · ${measured && typeof observed === 'number' ? `最近采集 ${new Date(observed * 1000).toLocaleTimeString('zh-CN', {hour12: false})}` : '等待真实响应采集'}`;
    }
  }

  /**
   * 只展示已验收计数和真实工作时间，区分当前目标与上一份交付。
   * @param {object|undefined} agent 当前账号视图。
   * @return {void}
   */
  function paintProgress(agent) {
    const progress = agent?.progress, bar = $('#projects-progress-bar');
    const known = Number.isInteger(progress?.completed) && Number.isInteger(progress?.remaining)
      && Number.isInteger(progress?.total) && progress.total >= 0;
    $('#projects-progress-text').textContent = known ? `${progress.completed} / ${progress.total} 项已通过` : '尚未采集';
    bar.classList.toggle('hidden', !known || progress.total === 0);
    if (known && progress.total > 0) bar.value = Math.min(100, progress.completed / progress.total * 100);
    else bar.removeAttribute('value');
    const readiness = known && Number.isInteger(progress.ready) && Number.isInteger(progress.waiting)
      ? ` · 可开始 ${progress.ready} 项 · 等待前置验收 ${progress.waiting} 项` : '';
    $('#projects-progress-detail').textContent = known ? `授权池内剩余 ${progress.remaining} 项工程目标${readiness} · 通过独立验收才计入完成` : '以独立验收通过的目标计数。';
    const work = agent?.work, unfinished = work && !['passed', 'stopped'].includes(work.status);
    $('#projects-target-label').textContent = !work || unfinished ? '当前目标' : work.status === 'passed' ? '最近完成目标' : '最近停止目标';
    $('#projects-current').innerHTML = work
      ? `<p class="projects-target-state">${unfinished ? escape(names[work.status] || work.status) : work.status === 'passed' ? '上一目标已验收通过' : '上一目标已停止'}</p><strong>${escape(work.goal)}</strong><p class="hint">${escape(work.project_key)} · 原会话 ${escape(work.session_id.slice(0, 8))}</p>`
      : '<p class="hint">尚未开始工程目标，Pi 会从授权项目池选择。</p>';
    $('#projects-budget').textContent = unfinished
      ? `当前目标累计 ${duration(progress?.elapsed_work_sec)} · 剩余预算 ${duration(progress?.remaining_work_sec)}` : '';
    const activity = agent?.activity;
    $('#projects-activity').textContent = activity?.text
      ? `${typeof activity.created_at === 'number' ? new Date(activity.created_at * 1000).toLocaleTimeString('zh-CN', {hour12: false}) + ' · ' : ''}${activity.text}` : '';
  }

  /**
   * 仅更新状态展示，避免实时推送覆盖尚未保存的表单内容。
   * @return {void}
   */
  function paintState() {
    const agent = agents.find(item => item.account_id === accountId);
    const pending = pendingActions.get(accountId), schedule = agent?.schedule, work = agent?.work;
    const unfinished = work && !['passed', 'stopped'].includes(work.status), admission = agent?.admission;
    const active = agent?.controller_active && ['running', 'waiting'].includes(agent.status);
    let status = agent ? names[agent.status] || agent.status : '保存项目池后即可启动 Pi';
    if (pending) status = pending.action === 'start' ? '正在启动 / 恢复 Pi…' : '正在收口当前执行…';
    else if (active) status = work?.status === 'verifying' ? '独立验收中'
      : unfinished ? 'Pi 指挥中' : 'Pi 指挥中 · 准备下一个目标';
    else if (schedule?.state === 'blocked' || agent?.status === 'blocked') status = '需要处理';
    else if (schedule?.state === 'completed') status = '项目池已完成';
    else if (schedule?.enabled) status = schedule.state === 'waiting' ? '等待运行条件' : '待机 · 已安排自动启动';
    $('#projects-state').textContent = status;
    $('#projects-overview').dataset.state = pending ? 'pending' : active ? 'running' : schedule?.state || agent?.status || 'off';
    $('#projects-message').textContent = agent?.message || '';
    $('#projects-admission').textContent = !agent ? '选择账号并保存项目池后，查看运行条件。'
      : admission?.allowed === false ? admission.message || '当前执行条件未满足。'
      : admission?.allowed === true ? `运行条件允许${admission.window?.timezone ? ` · 账号时区 ${admission.window.timezone}` : ''}` : '执行条件尚未采集。';
    let next = '选择账号并保存项目池。';
    if (agent) {
      if (pending) next = '控制操作已提交，请等待运行状态更新。';
      else if (active) next = work?.status === 'verifying' ? '等待独立验收结果，Pi 会依据事实决定是否返工。' : 'Pi 持续观察终端并推进；可在交互标签查看最近操作。';
      else if (schedule?.state === 'blocked' || agent.status === 'blocked') next = '处理等待原因后，重新保存计划或手动启动。';
      else if (schedule?.state === 'completed' || agent.progress?.remaining === 0) next = '授权项目池已完成，扩充项目池后继续。';
      else if (admission?.allowed === false) next = schedule?.enabled && admission.retryable ? '满足运行条件后自动恢复原目标。' : '运行条件解除后，手动启动或恢复。';
      else if (schedule?.enabled) next = '到达下次时间后自动检查，接续未完成目标。';
      else next = unfinished ? '点击“启动 / 恢复 Pi”继续原目标，累计预算保持不变。' : '点击“启动 / 恢复 Pi”，从授权池选择未完成目标。';
    }
    $('#projects-next-action').textContent = next;
    paintProgress(agent); paintQuota(admission);
    const usage = agent?.pi_usage;
    const native = agent?.claude_usage;
    const count = value => value === null || value === undefined ? '未采集' : value.toLocaleString();
    const piUsage = usage && `Pi${usage.complete === false ? '（已知小计）' : ''}：未缓存输入 ${count(usage.input_tokens)} · 缓存写入 ${count(usage.cache_write_tokens)} · 缓存读取 ${count(usage.cache_read_tokens)} · 输出 ${count(usage.output_tokens)}`;
    const nativeUsage = `Claude${native?.complete === false ? '（已知小计）' : ''}：未缓存输入 ${count(native?.input_tokens)} · 缓存写入 ${count(native?.cache_creation_input_tokens)} · 缓存读取 ${count(native?.cache_read_input_tokens)} · 输出 ${count(native?.output_tokens)}`;
    $('#projects-usage').textContent = usage ? `账号累计｜${piUsage}；${nativeUsage}` : '尚无模型调用';
    document.querySelectorAll('[data-pi-action]').forEach(button => {
      button.disabled = !agent || !!pending || (button.dataset.piAction === 'start' && agent.controller_active === true);
      button.setAttribute('aria-busy', String(!!pending));
      button.textContent = pending?.action === button.dataset.piAction
        ? {start: '正在启动…', pause: '正在暂停…', stop: '正在停止…'}[pending.action]
        : {start: '启动 / 恢复 Pi', pause: '暂停', stop: '停止当前目标'}[button.dataset.piAction];
    });
    paintSchedule(); paintScreen();
  }

  /**
   * 终端只接受当前目标的最新观察，切换目标时立即清除上一目标画面。
   * @param {object|null|undefined} observation 可选的最新终端事件。
   * @return {void}
   */
  function paintScreen(observation) {
    const work = agents.find(item => item.account_id === accountId)?.work;
    const workId = work?.id || null;
    if (workId !== screenWorkId || !screenEventId) {
      screenWorkId = workId; screenEventId = 0;
      $('#projects-screen').textContent = workId ? '等待当前目标的终端观察。' : '尚无工程目标。';
      $('#projects-screen-status').textContent = workId
        ? `${work.project_key} · ${work.objective_id} · 等待最新画面` : '选择账号后查看当前目标的最新画面。';
    }
    if (!observation || observation.work_id !== workId || observation.id <= screenEventId) return;
    screenEventId = observation.id;
    $('#projects-screen').textContent = observation.payload.screen || '终端已释放，原会话保留。';
    $('#projects-screen-status').textContent = `${work.project_key} · ${work.objective_id} · 最近观察 ${new Date(observation.created_at * 1000).toLocaleString('zh-CN', {hour12: false})}`;
  }

  /**
   * 接收实时记录；旧页保持位置，新记录通过提示返回最新页。
   * @param {string} kind 交互或工程记录。
   * @param {Array<object>} items 已确认的增量记录。
   * @return {void}
   */
  function receiveRecords(kind, items) {
    if (!items.length) return;
    const record = recordPages[kind];
    if (record.loading) { record.incoming.push(...items); return; }
    if (record.index > 0) {
      for (const item of items) {
        let found = false;
        for (const page of record.pages) {
          const index = page.items.findIndex(previous => previous.id === item.id);
          if (index >= 0) { page.items[index] = item; found = true; }
        }
        if (!found) record.pending.add(item.id);
      }
    } else {
      const page = record.pages[0] || {items: [], next_before: null};
      const merged = Array.from(new Map([...page.items, ...items].map(item => [item.id, item])).values());
      merged.sort(kind === 'events' ? (left, right) => right.id - left.id
        : (left, right) => right.created_at - left.created_at || right.id.localeCompare(left.id));
      const visible = merged.slice(0, record.size), more = page.next_before !== null || merged.length > record.size;
      record.pages = [{items: visible, next_before: more && visible.length ? visible[visible.length - 1].id : null}];
      record.pending.clear();
    }
    paintRecords(kind);
  }

  /**
   * 使用稳定游标翻页，账号切换后丢弃旧请求；新数据不挤动正在阅读的旧页。
   * @param {string} kind 交互或工程记录。
   * @param {string} direction 上一页、下一页或返回最新。
   * @return {Promise<void>} 当前页已更新。
   */
  async function loadPage(kind, direction) {
    const record = recordPages[kind];
    if (!accountId || record.loading) return;
    let target = direction === 'next' ? record.index + 1 : direction === 'previous' ? record.index - 1 : 0;
    if (target < 0) return;
    if (target === 0 && record.pending.size) direction = 'latest';
    if (direction !== 'latest' && record.pages[target]) {
      record.index = target; paintRecords(kind, true); return;
    }
    const before = direction === 'next' ? record.pages[record.index]?.next_before : null;
    if (direction === 'next' && before == null) return;
    const current = revision, selected = accountId, chosen = selection;
    const active = () => current === revision && selected === accountId && chosen === selection && recordPages[kind] === record;
    record.loading = true; record.incoming = []; paintPagination(kind);
    try {
      const path = kind === 'events' ? 'events' : 'work';
      const page = await api(`/projects/agents/${selected}/${path}/page?limit=${record.size}${before == null ? '' : '&before=' + encodeURIComponent(before)}`);
      if (!active()) return;
      if (direction === 'latest') { record.pages = [page]; record.index = 0; record.pending.clear(); }
      else { record.pages[target] = page; record.index = target; }
      paintRecords(kind, true);
    } finally {
      if (active()) {
        record.loading = false;
        const incoming = record.incoming; record.incoming = [];
        receiveRecords(kind, incoming); paintPagination(kind);
      }
    }
  }

  /**
   * 更新分页控件，明确最新排序、页大小和新记录数量。
   * @param {string} kind 交互或工程记录。
   * @return {void}
   */
  function paintPagination(kind) {
    const record = recordPages[kind], page = record.pages[record.index];
    $(`#projects-${kind}-page`).textContent = `${record.loading ? '加载中 · ' : ''}第 ${record.index + 1} 页 · 每页 ${record.size} 条 · 最新在前`;
    $(`#projects-${kind}-previous`).disabled = record.loading || record.index === 0;
    $(`#projects-${kind}-next`).disabled = record.loading || page?.next_before == null;
    $(`#projects-${kind}-latest`).disabled = record.loading || record.index === 0 && !record.pending.size;
    const notice = $(`#projects-${kind}-new`);
    notice.classList.toggle('hidden', !record.pending.size); notice.disabled = record.loading;
    notice.textContent = `有 ${record.pending.size} 条新${kind === 'events' ? '交互' : '工程记录'}，查看最新`;
  }

  /**
   * 显示当前页，实时插入时保留阅读位置；主动翻页时从页首开始。
   * @param {string} kind 交互或工程记录。
   * @param {boolean} resetScroll 是否回到当前页顶部。
   * @return {void}
   */
  function paintRecords(kind, resetScroll = false) {
    const element = $(`#projects-${kind}`), top = element.scrollTop, height = element.scrollHeight;
    if (kind === 'events') paintEvents();
    else paintHistory(recordPages.history.pages[recordPages.history.index]?.items || []);
    paintPagination(kind);
    element.scrollTop = resetScroll ? 0 : top > 40 ? top + Math.max(0, element.scrollHeight - height) : top;
  }

  /**
   * 显示真实观察和操作事件，全部外部文本均转义。
   * @return {void}
   */
  function paintEvents() {
    const element = $('#projects-events');
    const labels = {pi: 'Pi', input: '发送到 Claude', started: '原生会话', error: '异常',
      verification: '独立验收', input_unknown: '输入待核对', reconciled: '人工核对', recovery: '模型恢复', manual_retry: '人工重试',
      guide_loaded: '业务指南'};
    element.innerHTML = (recordPages.events.pages[recordPages.events.index]?.items || []).map(item => {
      const payload = item.payload;
      let message = payload.text || payload.message;
      if (item.kind === 'recovery') {
        const seconds = Math.ceil((Number(payload.delay_ms) || 0) / 1000);
        message = payload.message || {retry: `模型暂不可用，约 ${seconds} 秒后重试。`,
          fallback: `模型暂不可用，约 ${seconds} 秒后切换到 ${payload.model}。`,
          recovered: '模型已恢复，继续原会话。', reset: '已重置自动恢复次数，继续原会话。',
          scheduled: '已安排自动恢复，原会话和预算已保留。', exhausted: '自动恢复已用尽，请人工检查。',
          paused: '自动恢复已暂停，原会话已保留。'}[payload.phase] || '正在恢复模型，原会话已保留。';
      } else if (item.kind === 'manual_retry') message ||= '已人工确认重试，继续原目标和原会话。';
      else if (item.kind === 'guide_loaded') message = '本轮已将保存的追加业务指南与默认指南一起交给 Pi。';
      return `<li data-event-id="${escape(item.id)}"><small class="muted">${escape(new Date(item.created_at * 1000).toLocaleString('zh-CN', {hour12: false}))} · ${escape(labels[item.kind] || item.kind)}</small><pre>${escape(message || JSON.stringify(payload, null, 2))}</pre></li>`;
    }).join('')
      || '<li class="hint">启动后在这里查看 Pi 的判断、实际输入和验收结果。</li>';
  }

  /**
   * 显示已保存的新工作记录，单独计量工程完成与执行暂停。
   * @param {Array<object>} rows 工作摘要。
   * @return {void}
   */
  function paintHistory(rows) {
    $('#projects-history').innerHTML = rows.map(item => `<div class="projects-history-row"><strong>${escape(item.project_key)}</strong><span>${escape(item.goal)}<small class="hint">${escape(new Date(item.created_at * 1000).toLocaleString('zh-CN', {hour12: false}))}</small></span><span>${escape(names[item.status] || item.status)}</span><button type="button" class="btn btn-sm" data-work="${escape(item.id)}">查看交付</button></div>`).join('') || '<p class="hint">尚无新工作记录。</p>';
    document.querySelectorAll('[data-work]').forEach(button => {
      button.onclick = () => perform(async () => {
        const current = revision, selected = accountId;
        const detail = await api('/projects/work/' + encodeURIComponent(button.dataset.work));
        if (current !== revision || selected !== accountId) return;
        $('#projects-delivery').open = true;
        $('#projects-delivery-title').textContent = detail.work.goal;
        $('#projects-submissions').innerHTML = detail.submissions.map(item => `<button class="btn btn-sm" type="button" data-submission="${escape(item.id)}">${escape(names[item.status] || item.status)} · ${escape(new Date(item.created_at * 1000).toLocaleString())}</button>`).join(' ') || '<p class="hint">尚未提交独立验收。</p>';
        $('#projects-delivery-files').innerHTML = ''; $('#projects-delivery-preview').textContent = '';
        document.querySelectorAll('[data-submission]').forEach(submission => {
          submission.onclick = () => perform(async () => {
            const value = await api('/projects/submissions/' + encodeURIComponent(submission.dataset.submission));
            if (current !== revision || selected !== accountId) return;
            $('#projects-delivery-preview').textContent = JSON.stringify(value.report, null, 2);
            $('#projects-delivery-files').innerHTML = value.files.map(file => `<button type="button" class="btn btn-sm" data-candidate-path="${escape(file.path)}"${file.deleted ? ' disabled' : ''}>${escape(file.path)}${file.deleted ? '（已删除）' : ''}</button>`).join(' ');
            document.querySelectorAll('[data-candidate-path]').forEach(file => {
              file.onclick = () => perform(async () => {
                const preview = await api(`/projects/submissions/${encodeURIComponent(value.id)}?path=${encodeURIComponent(file.dataset.candidatePath)}`);
                if (current === revision && selected === accountId) $('#projects-delivery-preview').textContent = preview.text ?? preview.message;
              });
            });
          });
        });
      });
    });
  }

  /**
   * 允许用户在暂停后核对未知输入，操作文本始终保留。
   * @return {Promise<void>} 对账面板更新完成。
   */
  async function loadReconciliation() {
    const selected = accountId, current = revision;
    if (!selected) return;
    const rows = await api(`/projects/agents/${selected}/actions`);
    if (current !== revision || selected !== accountId) return;
    $('#projects-reconciliation').classList.toggle('hidden', !rows.length);
    $('#projects-actions').innerHTML = rows.map(item => `<div class="batch-panel"><pre>${escape(item.request.text || JSON.stringify(item.request.keys))}</pre><p class="hint">核对原终端和会话后记录事实。核对不会自动恢复 Pi。</p><button type="button" class="btn btn-sm" data-reconcile="${escape(item.id)}" data-sent="true">确认已发送</button> <button type="button" class="btn btn-sm" data-reconcile="${escape(item.id)}" data-sent="false">确认未发送</button></div>`).join('');
    document.querySelectorAll('[data-reconcile]').forEach(button => {
      button.onclick = () => perform(async () => {
        updateAgents(await api(`/projects/agents/${selected}/reconcile`, {method: 'POST', body: JSON.stringify({
          operation_id: button.dataset.reconcile, sent: button.dataset.sent === 'true',
        })}));
        await loadReconciliation(); paintState();
      });
    });
  }

  /**
   * 加载已保存的模型配置，密钥字段始终保持空白。
   * @return {Promise<void>} 脱敏配置加载完成。
   */
  async function loadModel() {
    const current = revision;
    const value = await api('/settings/project-requester');
    if (current !== revision) return;
    const form = $('#projects-model-form');
    form.elements.base_url.value = value.base_url;
    form.elements.models.value = value.models.join('\n');
    form.elements.api_key.value = '';
    $('#projects-model-status').textContent = value.ready ? `配置已就绪 · ${value.api_key_configured ? '密钥已配置' : '无密钥'}；启动或恢复的 Pi 使用该配置。` : value.error || '请配置支持流式响应和工具调用的外接模型。';
  }

  /**
   * 保存后续 Pi 使用的模型配置，不重建已有 Claude 会话。
   * @return {Promise<void>} 模型配置保存完成。
   */
  async function saveModel() {
    const form = $('#projects-model-form');
    await api('/settings/project-requester', {method: 'PUT', body: JSON.stringify({
      base_url: form.elements.base_url.value, api_key: form.elements.api_key.value || null,
      models: form.elements.models.value.split('\n').map(value => value.trim()).filter(Boolean),
    })});
    await loadModel(); feedback('Pi 模型配置已保存；在途控制者保留原配置，暂停后恢复即可采用新配置。');
  }

  return {mount, unmount};
})();
