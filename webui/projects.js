/** 新 Projects：围绕账号 Pi、真实终端与工作记录组织界面。 */
window.ProjectsUI = (() => {
  let api, prefix, source, accountId = null, agents = [], catalog = [], accounts = [], cursor = 0;
  let revision = 0, selection = 0, timeline = [], scheduleClock = null;
  const $ = selector => document.querySelector(selector);
  const escape = value => String(value ?? '').replace(/[&<>"']/g, character =>
    ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[character]));
  const names = {off: '未启动', running: 'Pi 指挥中', waiting: '等待执行条件', paused: '已暂停',
    blocked: '需要处理', ready: '待开始', verifying: '独立验收中', passed: '验收通过', stopped: '已停止'};

  /**
   * 在当前页面显示操作结果，页面切换后不再写入旧 DOM。
   * @param {string} message 用户可读消息。
   * @return {void}
   */
  function feedback(message) {
    const element = $('#projects-feedback');
    if (element) { element.textContent = message; element.classList.toggle('hidden', !message); }
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
    document.querySelectorAll('[data-pi-action]').forEach(button => {
      button.onclick = () => perform(async () => {
        if (!accountId) throw new Error('请先选择并保存账号项目池');
        const result = await api(`/projects/agents/${accountId}/${button.dataset.piAction}`, {method: 'POST'});
        updateAgents(result); paintState(); await loadReconciliation();
      });
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
    cursor = 0; timeline = []; accountId = null;
  }

  /**
   * 更新当前账号摘要，保持表单编辑及目录滚动位置。
   * @param {object} value 后端控制摘要。
   * @return {void}
   */
  function updateAgents(value) {
    for (const agent of value.agents) {
      const index = agents.findIndex(item => item.account_id === agent.account_id);
      if (index < 0) agents.push(agent); else agents[index] = agent;
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
    accountId = id || null; cursor = 0; timeline = [];
    const agent = agents.find(item => item.account_id === accountId);
    const form = $('#projects-agent-form');
    form.elements.instructions.value = agent?.instructions || '';
    form.elements.budget_minutes.value = (agent?.budget_sec || 3600) / 60;
    fillSchedule();
    paintCatalog(agent?.project_keys || []); paintState(); paintEvents();
    $('#projects-screen').textContent = '等待 Pi 观察 Claude Code 终端。';
    if (!accountId) return;
    const selected = accountId, current = revision;
    await perform(async () => {
      const [history] = await Promise.all([api(`/projects/agents/${selected}/work`), loadReconciliation()]);
      if (current !== revision || selected !== accountId || request !== selection) return;
      paintHistory(history);
      source = new EventSource(`${prefix}/api/projects/stream?account_id=${selected}`);
      source.addEventListener('update', event => {
        if (current !== revision || selected !== accountId || request !== selection) return;
        try {
          const payload = JSON.parse(event.data);
          updateAgents(payload.state);
          for (const item of payload.events) {
            if (item.id <= cursor) continue;
            cursor = item.id;
            if (item.kind === 'observation') $('#projects-screen').textContent = item.payload.screen || '终端已释放，原会话保留。';
            else if (item.kind !== 'usage') timeline.push(item);
          }
          timeline = timeline.slice(-80);
          paintState(); paintEvents();
          if (payload.events.some(item => ['verification', 'input_unknown', 'reconciled'].includes(item.kind))) {
            api(`/projects/agents/${selected}/work`).then(rows => {
              if (current === revision && selected === accountId) paintHistory(rows);
            }).catch(error => feedback(error.message));
            loadReconciliation().catch(error => feedback(error.message));
          }
        } catch { feedback('Pi 事件流暂不可用，请刷新核对状态'); }
      });
      source.onerror = () => {
        if (current === revision && selected === accountId) feedback('连接中断，正在重新连接；Claude 会话仍保留。');
      };
    });
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
      next.textContent = '';
    }
  }

  /**
   * 仅更新状态展示，避免实时推送覆盖尚未保存的表单内容。
   * @return {void}
   */
  function paintState() {
    const agent = agents.find(item => item.account_id === accountId);
    $('#projects-state').textContent = agent ? names[agent.status] || agent.status : '保存项目池后即可启动 Pi';
    $('#projects-message').textContent = agent?.message || '';
    const work = agent?.work;
    $('#projects-current').innerHTML = work ? `<strong>${escape(work.goal)}</strong><p class="hint">${escape(work.project_key)} · ${escape(names[work.status] || work.status)} · 原会话 ${escape(work.session_id.slice(0, 8))}</p><p class="hint">${escape(work.message || '')}</p>`
      : '<p class="hint">Pi 将从授权项目池选择工程目标，并在实际终端中推进。</p>';
    const usage = agent?.pi_usage;
    const native = agent?.claude_usage;
    const count = value => value === null || value === undefined ? '未采集' : value.toLocaleString();
    $('#projects-usage').textContent = usage ? `Pi${usage.complete === false ? '（已知小计）' : ''}：输入 ${count(usage.input_tokens)} · 输出 ${count(usage.output_tokens)} · 缓存 ${count(usage.cache_read_tokens)}；Claude：输入 ${count(native?.input_tokens)} · 输出 ${count(native?.output_tokens)} · 缓存 ${count(native?.cache_read_input_tokens)}` : '尚无模型调用';
    document.querySelectorAll('[data-pi-action]').forEach(button => {
      button.disabled = !agent || (button.dataset.piAction === 'start' && agent.controller_active === true);
    });
    paintSchedule();
  }

  /**
   * 显示真实观察和操作事件，全部外部文本均转义。
   * @return {void}
   */
  function paintEvents() {
    const element = $('#projects-events');
    const follow = element.scrollHeight - element.scrollTop - element.clientHeight < 40;
    const labels = {pi: 'Pi', input: '发送到 Claude', started: '原生会话', error: '异常',
      verification: '独立验收', input_unknown: '输入待核对', reconciled: '人工核对'};
    element.innerHTML = timeline.map(item => `<li><small class="muted">${escape(new Date(item.created_at * 1000).toLocaleTimeString())} · ${escape(labels[item.kind] || item.kind)}</small><pre>${escape(item.payload.text || item.payload.message || JSON.stringify(item.payload, null, 2))}</pre></li>`).join('')
      || '<li class="hint">启动后在这里查看 Pi 的判断、实际输入和验收结果。</li>';
    if (follow) element.scrollTop = element.scrollHeight;
  }

  /**
   * 显示已保存的新工作记录，单独计量工程完成与执行暂停。
   * @param {Array<object>} rows 工作摘要。
   * @return {void}
   */
  function paintHistory(rows) {
    $('#projects-history').innerHTML = rows.map(item => `<div class="projects-history-row"><strong>${escape(item.project_key)}</strong><span>${escape(item.goal)}</span><span>${escape(names[item.status] || item.status)}</span><button type="button" class="btn btn-sm" data-work="${escape(item.id)}">查看交付</button></div>`).join('') || '<p class="hint">尚无新工作记录。</p>';
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
