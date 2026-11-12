import { afterEach, expect, test } from 'bun:test';
import { mkdtemp, readdir, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { Database } from 'bun:sqlite';
import { LogStore } from '../../src/control/log-store';
import type { LogSnapshot, LogWriterConfig } from '../../src/control/log-schema';
import { RequestTrace } from '../../src/control/trace';
import { parseInput } from '../../src/shared/input';
import { prepareInput } from '../../src/control/header-policy';
import type { CaptureStage } from '../../src/shared/contracts';

const roots: string[] = [];
const stores: LogStore[] = [];
afterEach(async () => { for (const store of stores.splice(0)) await store.close(); for (const root of roots.splice(0)) await rm(root, { recursive: true, force: true }); });

function snapshot(id: string, ageDays = 0, text = '持久原文', state: 'success' | 'running' = 'success'): LogSnapshot {
  const createdAt = new Date(Date.now() - ageDays * 86400000).toISOString();
  return {
    request: { id, createdAt, finishedAt: state === 'running' ? null : createdAt, model: 'fixture', requestClass: 'main', sessionId: 'session-fixture', promptId: 'prompt-fixture', agentId: 'root-fixture', parentAgentId: null, state, httpStatus: 200, durationMs: 1, headersMs: 1, firstOutputMs: 1, mode: 'debug', engine: 'test/storage', binarySha256: null, error: null, captureError: null },
    context: { requestClass: 'main', sessionId: 'session-fixture', promptId: 'prompt-fixture', agentKind: 'main', agentId: 'root-fixture', querySource: 'sdk', source: 'bridge-default' },
    decisions: [],
    captures: [{ stage: 'ingress', attempt: 1, capturedAt: createdAt, source: 'test_fixture', representation: 'utf8', status: 'complete', observedBytes: Buffer.byteLength(text), storedBytes: Buffer.byteLength(text), sha256: null, text, headers: [], note: null }],
  };
}

async function open(config?: LogWriterConfig): Promise<{ store: LogStore; config: LogWriterConfig }> {
  if (!config) {
    const root = await mkdtemp(join(tmpdir(), 'ccrb-storage-test-')); roots.push(root);
    config = { dbPath: join(root, 'logs.sqlite'), bodyDir: join(root, 'bodies'), retainDays: 7, debugRetainDays: 3, maxBytes: 1024 * 1024 };
  }
  const store = new LogStore(config); await store.open(); stores.push(store);
  return { store, config };
}

test('正文先过期，摘要在各自保留期内仍然可查', async () => {
  const { store, config } = await open();
  store.record(snapshot('expired-all', 8)); store.record(snapshot('expired-body', 4)); store.record(snapshot('recent', 1));
  await store.flush();
  expect(await store.detail('expired-all')).toBeNull();
  const expired = await store.detail('expired-body');
  expect(expired?.captures[0]?.status).toBe('unavailable');
  expect(expired?.captures[0]?.text).toBeNull();
  expect(expired?.captures[0]?.note).toBe('原文已过保留期');
  expect((await store.detail('recent'))?.captures[0]?.text).toBe('持久原文');
  expect(await readdir(config.bodyDir)).toHaveLength(1);
});

test.each(['queued', 'running'] as const)('跨过正文和摘要保留期的 %s 请求保留到完成', async state => {
  const { store } = await open();
  for (const age of [4, 8]) {
    const value = snapshot('active-' + age, age, '执行中原文', 'running');
    value.request.state = state;
    store.record(value); await store.flush();
    const active = await store.detail(value.request.id);
    expect(active?.request.state).toBe(state);
    expect(active?.captures[0]?.text).toBe('执行中原文');
    value.request.state = 'success';
    value.request.finishedAt = new Date().toISOString();
    store.record(value); await store.flush();
    const finished = await store.detail(value.request.id);
    if (age > 7) expect(finished).toBeNull();
    else {
      expect(finished?.captures[0]?.status).toBe('unavailable');
      expect(finished?.captures[0]?.text).toBeNull();
    }
  }
  expect(store.error).toBeNull();
});

test('容量按 UTF-8 载荷计算，超限回收最旧的已完成请求', async () => {
  const initial = await open(); const config = { ...initial.config, maxBytes: 7500 };
  await initial.store.close(); stores.splice(stores.indexOf(initial.store), 1);
  const { store } = await open(config);
  for (let i = 0; i < 6; i++) store.record(snapshot('quota-' + i, (6 - i) / 24, '正文'.repeat(300)));
  await store.flush();
  expect(store.error).toBeNull();
  const result = store.list();
  expect(result.total).toBeGreaterThan(0); expect(result.total).toBeLessThan(6);
  expect(await store.detail('quota-0')).toBeNull();
  expect((await store.detail('quota-5'))?.captures[0]?.text).toBe('正文'.repeat(300));
  const db = new Database(config.dbPath, { readonly: true });
  try {
    const usage = db.query<{ bytes: number }, []>('SELECT COALESCE((SELECT SUM(LENGTH(CAST(payload AS BLOB))+LENGTH(CAST(context_json AS BLOB))+LENGTH(CAST(decisions_json AS BLOB))) FROM requests),0)+COALESCE((SELECT SUM(LENGTH(CAST(payload AS BLOB))+json_extract(payload,"$.storedBytes")) FROM captures),0) AS bytes').get();
    expect(usage!.bytes).toBeLessThanOrEqual(config.maxBytes);
  } finally { db.close(); }
});

test('控制进程重启后保留详情，并把未确认的运行中记录标为未完成', async () => {
  const first = await open();
  first.store.record(snapshot('persisted')); first.store.record(snapshot('unfinished', 0, '请求前缀', 'running')); await first.store.flush();
  await first.store.close(); stores.splice(stores.indexOf(first.store), 1);
  const { store } = await open(first.config);
  expect((await store.detail('persisted'))?.captures[0]?.text).toBe('持久原文');
  const unfinished = await store.detail('unfinished');
  expect(unfinished?.request.state).toBe('incomplete');
  expect(unfinished?.request.captureError).toContain('没有保存完整终态');
  expect(unfinished?.context?.agentId).toBe('root-fixture');
});

test('正文文件损坏或丢失会明确标出采集失败', async () => {
  const { store, config } = await open();
  store.record(snapshot('missing-body')); await store.flush();
  const [file] = await readdir(config.bodyDir); await rm(join(config.bodyDir, file!));
  const detail = await store.detail('missing-body');
  expect(detail?.captures[0]?.status).toBe('failed');
  expect(detail?.captures[0]?.text).toBeNull();
});

/** 生成可从每个阶段独立辨认代次的快照，验证发布一致性而非写入顺序。
 * @param id 合成请求标识。
 * @param generation 快照代次，零代表运行中。
 * @param bytes 正文填充大小。
 * @return 含五个阶段的独立快照。
 */
function versionedSnapshot(id: string, generation: number, bytes = 0): LogSnapshot {
  const value = snapshot(id, 0, '', generation ? 'success' : 'running');
  value.request.durationMs = generation;
  value.context!.promptId = 'generation-' + generation;
  const stages: CaptureStage[] = ['ingress', 'header_policy', 'cc_prepared', 'wire_final', 'upstream_response'];
  const text = generation + ':' + 'x'.repeat(bytes);
  value.captures = stages.map(stage => ({ ...value.captures[0]!, stage, note: String(generation), text, observedBytes: Buffer.byteLength(text), storedBytes: Buffer.byteLength(text), status: !generation && stage === 'upstream_response' ? 'incomplete' : 'complete' }));
  return value;
}

test('并发读取请求行和五阶段时只看到同一代已提交快照', async () => {
  const root = await mkdtemp(join(tmpdir(), 'ccrb-snapshot-')); roots.push(root);
  const { store } = await open({ dbPath: join(root, 'logs.sqlite'), bodyDir: join(root, 'bodies'), retainDays: 7, debugRetainDays: 3, maxBytes: 32 * 1024 * 1024 });
  store.record(versionedSnapshot('atomic', 0)); await store.flush();
  for (let generation = 1; generation <= 4; generation++) {
    store.record(versionedSnapshot('atomic', generation, 1024 * 1024));
    for (let read = 0; read < 100; read++) {
      const detail = await store.detail('atomic');
      expect(detail).not.toBeNull();
      const observed = detail!.request.durationMs!;
      expect(detail!.context!.promptId).toBe('generation-' + observed);
      expect(detail!.captures).toHaveLength(5);
      for (const capture of detail!.captures) {
        expect(capture.note).toBe(String(observed));
        expect(capture.text?.startsWith(observed + ':')).toBe(true);
      }
      if (observed === generation) break;
    }
    await store.flush();
    expect((await store.detail('atomic'))?.request.durationMs).toBe(generation);
  }
  expect(store.error).toBeNull();
});

test('后续阶段写入失败时请求行与所有阶段整组回滚，旧正文仍可读', async () => {
  const { store, config } = await open();
  store.record(versionedSnapshot('rollback', 0)); await store.flush();
  const before = await store.detail('rollback');
  const db = new Database(config.dbPath);
  try {
    // 在最后一个阶段拒绝更新，确保此前请求行和阶段也必须回滚。
    db.exec("CREATE TRIGGER reject_final_stage BEFORE UPDATE ON captures WHEN NEW.stage='upstream_response' BEGIN SELECT RAISE(ABORT, 'synthetic_stage_failure'); END");
    store.record(versionedSnapshot('rollback', 1)); await store.flush();
    expect(store.error).not.toBeNull();
    const after = await store.detail('rollback');
    expect(after?.request.state).toBe('running');
    expect(after?.request.captureError).not.toBeNull();
    expect(after?.context).toEqual(before?.context);
    expect(after?.captures).toEqual(before?.captures);
  } finally { db.close(); }
});

/** 创建同会话的子代理或启动证据快照。
 * @param id 请求标识。
 * @param child 是否为子代理请求。
 * @param agentId 规范代理标识。
 * @return 独立快照，不修改既有记录。
 */
function associationSnapshot(id: string, child: boolean, agentId = child ? 'child-a' : 'root-a'): LogSnapshot {
  const value = snapshot(id);
  value.request.agentId = agentId; value.context!.agentId = agentId;
  if (child) {
    value.request.requestClass = 'subagent'; value.context!.requestClass = 'subagent'; value.context!.agentKind = 'subagent';
  } else {
    value.request.agentLaunches = { state: 'complete', links: [{ childAgentId: 'child-a', parentAgentId: agentId, agentType: 'Explore', toolUseId: 'toolu-a' }] };
  }
  return value;
}

test('后到启动证据在刷新时关联，跨会话隔离，重启后无需工具正文', async () => {
  const initial = await open(); const child = associationSnapshot('child', true);
  initial.store.record(child); await initial.store.flush();
  const before = await initial.store.detail('child');
  expect(before?.agentAssociation).toMatchObject({ state: 'unknown', parentAgentId: null, agentType: null });
  const unrelated = associationSnapshot('other-session', false, 'unrelated');
  unrelated.request.sessionId = unrelated.context!.sessionId = 'another-session';
  initial.store.record(unrelated); initial.store.record(associationSnapshot('parent-evidence', false)); await initial.store.flush();
  const linked = await initial.store.detail('child');
  expect(linked?.agentAssociation).toMatchObject({ state: 'linked', parentAgentId: 'root-a', agentType: 'Explore', evidence: [{ requestId: 'parent-evidence', toolUseId: 'toolu-a' }] });
  expect(linked?.request).toEqual(before?.request); expect(linked?.context).toEqual(before?.context); expect(linked?.captures).toEqual(before?.captures);
  const second = associationSnapshot('second-child', true, 'child-b'), secondParent = associationSnapshot('second-parent', false, 'root-b');
  secondParent.request.agentLaunches!.links[0]!.childAgentId = 'child-b';
  secondParent.request.agentLaunches!.links[0]!.agentType = 'Plan';
  initial.store.record(second); initial.store.record(secondParent); await initial.store.flush();
  expect((await initial.store.detail('second-child'))?.agentAssociation).toMatchObject({ state: 'linked', parentAgentId: 'root-b', agentType: 'Plan' });
  expect((await initial.store.detail('child'))?.agentAssociation).toEqual(linked?.agentAssociation);
  await initial.store.close(); stores.splice(stores.indexOf(initial.store), 1);
  const { store } = await open(initial.config);
  expect((await store.detail('child'))?.agentAssociation).toEqual(linked?.agentAssociation);
});

test('多层代理只取直接父上下文，冲突不任意覆盖，显式值保持', async () => {
  const { store } = await open();
  const middle = associationSnapshot('middle', true, 'middle-a');
  middle.request.agentLaunches = { state: 'complete', links: [{ childAgentId: 'child-a', parentAgentId: 'middle-a', agentType: 'Explore', toolUseId: 'toolu-nested' }] };
  const child = associationSnapshot('child', true);
  store.record(middle); store.record(child); await store.flush();
  expect((await store.detail('child'))?.agentAssociation).toMatchObject({ state: 'linked', parentAgentId: 'middle-a' });
  store.record(associationSnapshot('conflicting-parent', false)); await store.flush();
  expect((await store.detail('child'))?.agentAssociation).toMatchObject({ state: 'conflict', parentAgentId: null, agentType: 'Explore' });
  child.context!.parentAgentId = 'explicit'; child.context!.agentType = 'explicit-type'; child.request.parentAgentId = 'explicit';
  store.record(child); await store.flush();
  expect((await store.detail('child'))?.agentAssociation).toMatchObject({ state: 'conflict', parentAgentId: 'explicit', agentType: 'explicit-type', parentSource: 'explicit', typeSource: 'explicit' });
});

test('摘要证据随保留期清理，查询上限和提取缺口均不冒充完整关联', async () => {
  const { store, config } = await open();
  store.record(associationSnapshot('child', true)); store.record(associationSnapshot('parent', false)); await store.flush();
  expect((await store.detail('child'))?.agentAssociation?.state).toBe('linked');
  // 只改变测试库的过期列，再触发既有清理器；不靠保留在内存中的关系绕过保留期。
  const db = new Database(config.dbPath);
  db.query('UPDATE requests SET created_at=? WHERE id=?').run(new Date(Date.now() - 8 * 86400000).toISOString(), 'parent'); db.close();
  store.record(snapshot('cleanup-trigger')); await store.flush();
  expect((await store.detail('child'))?.agentAssociation?.state).toBe('unknown');
  for (let i = 0; i < 33; i++) { store.record(associationSnapshot('evidence-' + i, false)); await store.flush(); }
  expect((await store.detail('child'))?.agentAssociation?.state).toBe('linked');
  for (let i = 0; i < 33; i++) {
    const distinct = associationSnapshot('distinct-' + i, false); distinct.request.agentLaunches!.links[0]!.toolUseId = 'toolu-' + i;
    store.record(distinct); await store.flush();
  }
  expect((await store.detail('child'))?.agentAssociation).toMatchObject({ state: 'incomplete', parentAgentId: null, agentType: null });
  const incomplete = associationSnapshot('partial', false); incomplete.request.agentLaunches!.state = 'incomplete';
  store.record(incomplete); await store.flush();
  expect((await store.detail('child'))?.agentAssociation?.state).toBe('incomplete');
  const damaged = new Database(config.dbPath);
  damaged.query('UPDATE requests SET payload=? WHERE id=?').run(JSON.stringify({ ...snapshot('cleanup-trigger').request, agentLaunches: { state: 'complete', links: ['not-json'] } }), 'cleanup-trigger');
  damaged.close();
  expect((await store.detail('child'))?.agentAssociation?.state).toBe('incomplete');
});

test('summary 保留有界关联元数据且脱敏，off 不保存新证据', async () => {
  const { store } = await open();
  const session = '11111111-1111-4111-8111-111111111111';
  const text = 'Async agent launched successfully. (This tool result is internal metadata — never quote or paste any part of it, including the agentId below, into a user-facing reply.)\nagentId: child-a (internal ID - do not mention to user.)\nsummary-secret-canary';
  const body = { model: 'fixture', system: [{ type: 'text', text: 'x-anthropic-billing-header: cc_version=2.1.293.abc; cc_entrypoint=cli;' }], metadata: { user_id: JSON.stringify({ device_id: 'a'.repeat(64), account_uuid: '', session_id: session }) }, messages: [{ role: 'assistant', content: [{ type: 'tool_use', id: 'toolu-a', name: 'Agent', input: { subagent_type: 'Explore' } }] }, { role: 'user', content: [{ type: 'tool_result', tool_use_id: 'toolu-a', content: [{ type: 'text', text }] }] }] };
  for (const mode of ['summary', 'off'] as const) {
    const prepared = prepareInput(parseInput({ request_id: 'trace-' + mode, body }, [], 'local_base_url'));
    const trace = new RequestTrace(prepared, body, [], store, { mode, maxBodyBytes: 1024, engine: 'test/fixture', secrets: { token: 'summary-secret-canary' } });
    trace.finish('error'); await store.flush();
    const detail = await store.detail('trace-' + mode);
    if (mode === 'off') expect(detail).toBeNull();
    else { expect(detail?.request.agentLaunches?.links).toHaveLength(1); expect(detail?.captures.every(c => c.text === null)).toBe(true); expect(JSON.stringify(detail)).not.toContain('summary-secret-canary'); }
  }
  const hiddenId = prepareInput(parseInput({ request_id: 'hidden-agent-id', body }, [], 'local_base_url'));
  new RequestTrace(hiddenId, body, [], store, { mode: 'summary', maxBodyBytes: 1024, engine: 'test/fixture', secrets: { token: 'child-a' } }).finish('error');
  await store.flush();
  expect((await store.detail('hidden-agent-id'))?.request.agentLaunches).toEqual({ state: 'incomplete', links: [] });
});
