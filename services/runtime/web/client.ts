import type { CaptureRecord, NativeClassification, RequestDetail, RequestRow } from '../src/shared/contracts';
import { decodeLogDetail, decodeLogList } from '../src/shared/log-api';
import { isObject } from '../src/shared/errors';

function get<T extends HTMLElement>(id: string): T {
  const value = document.getElementById(id);
  if (!value) throw new Error('页面元素缺失：' + id);
  return value as T;
}
function element<K extends keyof HTMLElementTagNameMap>(tag: K, text?: string, className?: string): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

const form = get<HTMLFormElement>('filters');
const dialog = get<HTMLDialogElement>('detail');
const content = get('detail-content');
const STATES: Record<string, string> = { queued: '等待中', running: '执行中', success: '成功', http_error: '上游 HTTP 错误', stream_error: '上游响应错误', incomplete: '终态未确认', canceled: '已取消', error: '本地错误' };
const CLASSES: Record<string, string> = { main: '主会话', subagent: '子代理', workflow: '工作流', compaction: '压缩', auxiliary: '辅助', side_reply: '旁路回复', unknown: '未解析' };
const PURPOSES: Record<NativeClassification['purpose'], string> = { auto_permission_classifier: '自动权限分类', session_title: '会话标题生成', compaction: '会话压缩' };
const STAGES: Record<string, string> = { ingress: '入站原文', header_policy: '头部处理', cc_prepared: 'CC 组装（中间值）', wire_final: '最终出站采样', upstream_response: '上游响应' };
const CAPTURE: Record<string, string> = { complete: '完整', truncated: '已截断', unavailable: '未采集', failed: '采集失败', incomplete: '未完整采集' };
const ACTIONS: Record<string, string> = { keep: '保留', drop: '删除', runtime: '运行时生成', context: '上下文映射' };
let offset = 0;
let total = 0;
let loading = false;
let listController: AbortController | null = null;
let detailController: AbortController | null = null;
let detail: RequestDetail | null = null;
let selectedTab = 'summary';
let selectedStage = 'ingress';
let toastTimer: ReturnType<typeof setTimeout>;

function toast(text: string): void {
  const box = get('toast'); box.textContent = text; box.hidden = false;
  (dialog.open ? dialog : document.body).append(box);
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { box.hidden = true; }, 2500);
}
function badge(label: string, tone = 'neutral'): HTMLElement { return element('span', label, 'badge ' + tone); }
function ms(value: number | null): string { return value === null ? '未观测' : value.toLocaleString() + ' ms'; }
function date(value: string | null): string { return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '未结束'; }
function tone(state: string): string { return state === 'success' || state === 'complete' ? '' : ['queued', 'running', 'unavailable', 'canceled'].includes(state) ? 'neutral' : state === 'truncated' || state === 'incomplete' ? 'warn' : 'bad'; }

async function json(path: string, signal?: AbortSignal): Promise<unknown> {
  const response = await fetch(path, { signal, cache: 'no-store' });
  const value: unknown = await response.json();
  if (!response.ok) throw new Error(isObject(value) && typeof value.error === 'string' ? value.error : '读取日志失败');
  return value;
}

function renderRows(rows: RequestRow[]): void {
  const body = get('rows'); body.replaceChildren();
  for (const row of rows) {
    const tr = element('tr');
    tr.append(element('td', date(row.createdAt), 'mono'));
    const idCell = element('td');
    const open = element('button', row.id.length > 25 ? row.id.slice(0, 25) + '…' : row.id, 'request-link');
    open.title = row.id; open.addEventListener('click', () => { void openDetail(row.id); });
    idCell.append(open, element('small', row.sessionId ? '会话 ' + row.sessionId.slice(0, 20) : '上下文未解析', 'secondary'));
    const model = element('td'); model.append(element('span', row.model), element('small', row.engine, 'secondary'));
    const kind = element('td'); kind.append(badge(CLASSES[row.requestClass] ?? row.requestClass));
    const state = element('td'); state.append(badge(STATES[row.state] ?? row.state, tone(row.state)));
    const capture = element('td'); capture.append(badge(row.captureError ? '采集异常' : row.mode === 'debug' ? '原文已开启' : row.mode === 'summary' ? '仅摘要' : '关闭', row.captureError ? 'bad' : 'neutral'));
    tr.append(idCell, model, kind, state, element('td', row.httpStatus === null ? '—' : String(row.httpStatus), 'mono'), element('td', ms(row.durationMs), 'mono'), capture);
    body.append(tr);
  }
  get('empty').hidden = rows.length !== 0;
  get('success-count').textContent = String(rows.filter(row => row.state === 'success').length);
  get('issue-count').textContent = String(rows.filter(row => row.state !== 'success').length);
}

async function loadList(): Promise<void> {
  listController?.abort(); const controller = new AbortController(); listController = controller;
  loading = true;
  try {
    const params = new URLSearchParams({ limit: '50', offset: String(offset) });
    for (const [key, raw] of new FormData(form)) {
      const value = String(raw).trim();
      if (!value) continue;
      params.set(key, key === 'since' || key === 'until' ? new Date(value).toISOString() : value);
    }
    const result = decodeLogList(await json('/api/logs?' + params, controller.signal));
    // 只让最后一轮筛选结果更新页面，防止慢请求覆盖新条件。
    if (listController !== controller) return;
    total = result.total; renderRows(result.rows);
    get('total-count').textContent = total.toLocaleString();
    get('list-note').textContent = '最近请求 · 当前显示 ' + result.rows.length + ' 条';
    get('page-note').textContent = total ? '第 ' + (offset / 50 + 1) + ' 页 · 共 ' + total.toLocaleString() + ' 条' : '没有匹配记录';
    get<HTMLButtonElement>('previous').disabled = offset === 0;
    get<HTMLButtonElement>('next').disabled = offset + 50 >= total;
    await loadHealth(controller.signal);
  } catch (error) {
    if (!controller.signal.aborted) { get('list-note').textContent = '日志加载失败'; toast(error instanceof Error ? error.message : '日志加载失败'); }
  } finally { if (listController === controller) loading = false; }
}

async function loadHealth(signal?: AbortSignal): Promise<void> {
  const health = await json('/api/health', signal);
  if (!isObject(health) || typeof health.engine !== 'string') return;
  const demo = health.engine.startsWith('demo');
  const label = get('engine-badge'); label.textContent = demo ? '演示模式 · 未调用上游' : '官方 Claude Code 2.1.293';
  label.className = 'badge ' + (demo ? 'warn' : '');
  get('log-mode').textContent = String(health.logMode);
  const verifierFailed = isObject(health.tlsVerifier) && health.tlsVerifier.state === 'failed';
  get('capture-hint').textContent = verifierFailed ? '最终 TLS 验证器不可用' : health.tlsCapture === 'verify' ? '最终 TLS 写出验证已开启（固定画像）' : health.nativeFinalCapture ? '独立 TLS 接收采样已开启' : '最终出站值未采集';
  const issue = health.captureError ?? (verifierFailed ? 'TLS 辅助程序失败，需要重启实例' : null);
  const warning = get('health-warning'); warning.hidden = !issue;
  warning.textContent = issue ? String(issue) + '；部分记录可能缺失，请勿据此判断上游请求是否成功。' : '';
}

async function openDetail(id: string, refresh = false): Promise<void> {
  detailController?.abort(); const controller = new AbortController(); detailController = controller;
  if (!refresh) { detail = null; selectedTab = 'summary'; selectedStage = 'ingress'; }
  get('detail-id').textContent = id;
  if (!dialog.open) dialog.showModal();
  content.replaceChildren(element('p', '正在读取请求详情…', 'section-note'));
  try {
    const result = decodeLogDetail(await json('/api/logs/' + encodeURIComponent(id), controller.signal));
    if (detailController !== controller || !dialog.open) return;
    detail = result; renderDetail();
  } catch (error) {
    if (!controller.signal.aborted) content.replaceChildren(element('p', error instanceof Error ? error.message : '无法读取详情', 'notice warning'));
  }
}

function field(label: string, value: unknown, wide = false): HTMLElement {
  const box = element('div', undefined, 'field' + (wide ? ' wide' : ''));
  box.append(element('span', label), element('strong', value === null || value === undefined || value === '' ? '未提供 / 未观测' : String(value), 'mono'));
  return box;
}
function summary(value: RequestDetail): void {
  const row = value.request;
  const grid = element('div', undefined, 'detail-grid');
  grid.append(field('接入路径', value.context?.inputFormat === 'claude_code' ? '原生 CC 正文接入' : value.context?.inputFormat === 'api' ? '普通 API 原生组装' : value.context ? '旧记录未注明' : '未解析'));
  const association = value.agentAssociation;
  const modelSelection = value.context?.modelSelection;
  const missingModel = value.context ? '旧记录未注明' : '未解析';
  grid.append(field('入站模型', modelSelection?.requested ?? missingModel), field('前置选择模型', modelSelection?.effective ?? row.model), field('模型选择来源', modelSelection ? modelSelection.source === 'startup_override' ? '本机启动配置' : '调用方请求' : missingModel));
  grid.append(field('状态', STATES[row.state] ?? row.state), field('HTTP 状态', row.httpStatus), field('模型', row.model), field('请求类别', CLASSES[row.requestClass] ?? row.requestClass), field('引擎', row.engine), field('上下文来源', value.context?.source === 'client' ? '调用方上下文' : value.context ? '桥接器默认' : '未解析'), field('开始时间', date(row.createdAt)), field('完成时间', date(row.finishedAt)), field('会话 ID', row.sessionId), field('Prompt ID', row.promptId), field('Agent ID', row.agentId), field('父 Agent ID', association?.parentAgentId ?? row.parentAgentId), field('二进制 SHA256', row.binarySha256, true));
  if (value.context?.inputFormat === 'claude_code') grid.append(field('请求用途', value.context.classification ? PURPOSES[value.context.classification.purpose] : '未识别特殊用途'));
  if (value.context?.classification) grid.append(field('归类来源', '固定 293 原生构造证据'));
  if (value.context?.agentKind === 'subagent' || value.context?.agentKind === 'teammate') {
    const source = { explicit: '调用方显式提供', client_tool_result: '客户端工具结果', unknown: '未知' };
    const states = { explicit: '显式关联', linked: '由证据关联', unknown: '关联信息未知', conflict: '关联证据冲突', incomplete: '关联证据不完整' };
    grid.append(field('代理类型', association?.agentType ?? value.context.agentType ?? '未知（客户端未提供且无可用证据）'), field('关联状态', association ? states[association.state] : '旧记录未注明'), field('父代理信息来源', association ? source[association.parentSource] : '未知'), field('代理类型来源', association ? source[association.typeSource] : '未知'));
    if (association?.parentSource === 'client_tool_result' || association?.typeSource === 'client_tool_result') grid.append(field('发生时父 Agent ID', row.parentAgentId), field('发生时代理类型', value.context.agentType));
  }
  content.append(grid);
  if (association?.state === 'conflict' || association?.state === 'incomplete') content.append(element('p', '关联证据存在冲突或缺口；显式提供的信息保留，未确认的字段不会自动补齐。', 'notice warning'));
  if (association?.evidence.length) {
    content.append(element('p', '以下客户端启动记录支持此关联视图；它们不代表当时已发送了缺失的关联字段。', 'section-note'));
    const evidence = element('div', undefined, 'detail-buttons');
    for (const id of new Set(association.evidence.map(e => e.requestId))) {
      const button = element('button', '证据请求 ' + id, 'button'); button.addEventListener('click', () => { void openDetail(id); }); evidence.append(button);
    }
    content.append(evidence);
  }
  if (row.error) content.append(element('p', row.error, 'notice warning'));
  if (row.captureError) content.append(element('p', row.captureError, 'notice warning'));
  const actions = element('div', undefined, 'detail-buttons');
  const related = element('button', '查看同会话请求', 'button'); related.disabled = !row.sessionId;
  related.addEventListener('click', () => { form.reset(); get<HTMLInputElement>('sessionId').value = row.sessionId; offset = 0; dialog.close(); void loadList(); });
  const copy = element('button', '复制请求 ID', 'button'); copy.addEventListener('click', () => { void copyText(row.id); });
  actions.append(related, copy); content.append(actions);
}
function headerDecisions(value: RequestDetail): void {
  content.append(element('p', '字段值与调用上下文分别处理。这里记录每项保留、删除或重新生成的原因，凭据不会显示。', 'section-note'));
  if (!value.decisions.length) { content.append(element('p', '此记录没有头部处理结果，可能在入口验证阶段被拒绝。', 'section-note')); return; }
  const table = element('table'); const head = element('thead'); const labels = element('tr');
  for (const label of ['请求头', '处理', '原因']) labels.append(element('th', label));
  head.append(labels); const body = element('tbody');
  for (const decision of value.decisions) {
    const tr = element('tr'); const action = element('td');
    action.append(badge(ACTIONS[decision.action] ?? decision.action, decision.action === 'drop' ? 'warn' : 'neutral'));
    tr.append(element('td', decision.name, 'mono'), action, element('td', decision.reason)); body.append(tr);
  }
  table.append(head, body); const scroll = element('div', undefined, 'table-scroll'); scroll.append(table); content.append(scroll);
}
function performanceView(value: RequestDetail): void {
  content.append(element('p', '总耗时从接收请求开始；响应头和首个有效输出从发送参数就绪开始。未观察到的数值保持为空。', 'section-note'));
  const grid = element('div', undefined, 'detail-grid');
  grid.append(field('总耗时', ms(value.request.durationMs)), field('发送至响应头', ms(value.request.headersMs)), field('发送至首个有效输出', ms(value.request.firstOutputMs)));
  for (const capture of value.captures) grid.append(field(STAGES[capture.stage] + ' · 采集时间', date(capture.capturedAt)));
  content.append(grid);
}
function pretty(text: string): string { try { return JSON.stringify(JSON.parse(text), null, 2); } catch { return text; } }
async function copyText(text: string): Promise<void> {
  try { await navigator.clipboard.writeText(text); toast('已复制脱敏内容'); } catch { toast('浏览器未允许复制，可选择文本手动复制'); }
}
function codeBlock(title: string, text: string | null): void {
  const heading = element('div', undefined, 'code-title'); heading.append(element('span', title));
  const copy = element('button', '复制', 'button'); copy.disabled = text === null; copy.addEventListener('click', () => { if (text !== null) void copyText(text); });
  heading.append(copy); content.append(heading, element('pre', text === null ? '未保存可展示原文' : pretty(text)));
}
function rawView(value: RequestDetail): void {
  const nav = element('div', undefined, 'capture-nav');
  for (const [stage, label] of Object.entries(STAGES)) {
    const capture = value.captures.find(item => item.stage === stage);
    const stageLabel = stage === 'cc_prepared' && value.context?.inputFormat === 'claude_code' ? '原生改写（中间值）' : label;
    const button = element('button', stageLabel + ' · ' + (capture ? CAPTURE[capture.status] ?? capture.status : '未采集'), 'button' + (selectedStage === stage ? ' active' : ''));
    button.addEventListener('click', () => { selectedStage = stage; renderDetail(); }); nav.append(button);
  }
  content.append(nav);
  const capture = value.captures.find(item => item.stage === selectedStage);
  if (!capture) { content.append(element('p', '未采集这个阶段的数据。', 'notice warning')); return; }
  captureView(capture);
}
function captureView(capture: CaptureRecord): void {
  const meta = element('div', undefined, 'capture-meta');
  meta.append(badge(CAPTURE[capture.status] ?? capture.status, tone(capture.status)), element('span', '来源：' + capture.source), element('span', '已观测 ' + capture.observedBytes.toLocaleString() + ' 字节 / 已保存 ' + capture.storedBytes.toLocaleString() + ' 字节'));
  content.append(meta, element('p', '内容表示：' + capture.representation + (capture.note ? '。' + capture.note : ''), 'section-note'));
  if (capture.sha256) content.append(field('原始观测 SHA256（脱敏展示内容不能直接作为校验输入）', capture.sha256, true));
  if (capture.headers.length) codeBlock('该采集位置的请求头 / 响应头（脱敏）', JSON.stringify(capture.headers));
  codeBlock('正文（脱敏）', capture.text);
}
function renderDetail(): void {
  if (!detail) return;
  content.replaceChildren();
  for (const tab of document.querySelectorAll<HTMLButtonElement>('[role=tab]')) {
    const active = tab.dataset.tab === selectedTab; tab.setAttribute('aria-selected', String(active)); tab.tabIndex = active ? 0 : -1;
    if (active) content.setAttribute('aria-labelledby', tab.id);
  }
  switch (selectedTab) {
    case 'summary': summary(detail); break;
    case 'headers': headerDecisions(detail); break;
    case 'performance': performanceView(detail); break;
    case 'raw': rawView(detail); break;
  }
}

form.addEventListener('submit', event => { event.preventDefault(); offset = 0; void loadList(); });
get('refresh').addEventListener('click', () => { void loadList(); });
get('reset-filters').addEventListener('click', () => { form.reset(); offset = 0; void loadList(); });
get('previous').addEventListener('click', () => { offset = Math.max(0, offset - 50); void loadList(); });
get('next').addEventListener('click', () => { if (offset + 50 < total) { offset += 50; void loadList(); } });
get('close-detail').addEventListener('click', () => dialog.close());
get('refresh-detail').addEventListener('click', () => { if (detail) void openDetail(detail.request.id, true); });
dialog.addEventListener('close', () => { detailController?.abort(); detail = null; });
const tabs = [...document.querySelectorAll<HTMLButtonElement>('[role=tab]')];
tabs.forEach((tab, index) => {
  tab.id = 'tab-' + tab.dataset.tab; tab.setAttribute('aria-controls', 'detail-content');
  tab.addEventListener('click', () => { selectedTab = tab.dataset.tab!; renderDetail(); });
  tab.addEventListener('keydown', event => {
    if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
    event.preventDefault(); const next = tabs[(index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length]!;
    next.focus(); next.click();
  });
});
setInterval(() => { if (get<HTMLInputElement>('auto-refresh').checked && !loading) void loadList(); }, 3000);
void loadList();
