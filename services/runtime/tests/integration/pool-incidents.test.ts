import { afterEach, expect, test } from 'bun:test';
import { lstat, mkdir, open, readFile, readdir, rename, rm, symlink, writeFile } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { PoolIncidentCollector, type PoolIncidentReport } from '../../scripts/testing/local-pool-incidents';
import { incidentFixture, incidentRow, incidentCapture, INCIDENT_STAGES, type IncidentFixture } from '../fixtures/pool-incidents';

const fixtures: IncidentFixture[] = [], collectors: PoolIncidentCollector[] = [];
afterEach(async () => { for (const collector of collectors.splice(0)) await collector.close(false); for (const fixture of fixtures.splice(0)) await fixture.close(); });

/** 建立归本测试清理的合成源。 @param runId 运行身份。 @return 真实表结构夹具。 */
async function fixture(runId?: string): Promise<IncidentFixture> { const value = await incidentFixture(runId); fixtures.push(value); return value; }
/** 打开归本测试清理的只读端。 @param source 合成源。 @return 采集器。 */
async function collector(source: IncidentFixture): Promise<PoolIncidentCollector> { const value = await PoolIncidentCollector.open({ runId: source.runId, directory: source.directory }); collectors.push(value); return value; }
/** 读取自有报告。 @param source 合成源。 @param id 请求 ID。 @return 安全报告。 */
async function report(source: IncidentFixture, id: string): Promise<PoolIncidentReport> { return JSON.parse(await readFile(join(source.directory, 'incidents/reports', id + '.json'), 'utf8')); }
/** 获取源的逻辑快照，不把只读 SQLite 的共享内存变化当作源数据写入。 @param source 合成源。 @return 对照字符串。 */
async function sourceSnapshot(source: IncidentFixture): Promise<string> {
  return JSON.stringify({ requests: source.db.query('SELECT * FROM requests ORDER BY id').all(), captures: source.db.query('SELECT * FROM captures ORDER BY request_id,stage').all(), ledger: await readFile(join(source.directory, 'ledger.json'), 'utf8') });
}

test('只读真实表补采，保持源记录与正文，独立检查存储和报告权限', async () => {
  const source = await fixture(), id = 'request-body', canary = 'body-private-canary-735159';
  const captures = INCIDENT_STAGES.map(incidentCapture), body = id + '-wire_final-1-9.txt';
  captures[3]!.storedBytes = Buffer.byteLength(canary); captures[3]!.text = canary;
  await writeFile(join(source.directory, 'data/bodies', body), canary, { mode: 0o600 });
  source.save(incidentRow(id), captures, { wire_final: body });
  await source.ledger([{ requestId: id, attempted: true, localStatus: 502, upstreamStatus: null, outcome: 'error', failureCode: 'UND_ERR_SOCKET', transportDiagnostics: { phase: 'awaiting_headers', bodySentObserved: true, connectionBytesWritten: 128, connectionBytesRead: 0 }, error: canary }]);
  const before = await sourceSnapshot(source), reader = await collector(source), status = await reader.collect();
  expect(status.written).toBe(1); expect(status.codes).toEqual([]);
  const value = await report(source, id);
  expect(value.captures.find(item => item.stage === 'wire_final')).toMatchObject({ recordedStatus: 'complete', bodyStorage: 'present' });
  expect(JSON.stringify(value)).not.toContain(canary);
  expect(await sourceSnapshot(source)).toBe(before); expect(await readFile(join(source.directory, 'data/bodies', body), 'utf8')).toBe(canary);
  expect((await lstat(join(source.directory, 'incidents'))).mode & 0o777).toBe(0o700);
  expect((await lstat(join(source.directory, 'incidents/reports', id + '.json'))).mode & 0o777).toBe(0o600);
  expect((await lstat(join(source.directory, 'incidents/status.json'))).mode & 0o777).toBe(0o600);
  await rm(join(source.directory, 'data/bodies', body));
  const supplement = await PoolIncidentCollector.open({ runId: source.runId, directory: source.directory, output: join(source.directory, 'supplement') }); collectors.push(supplement);
  await supplement.collect(id);
  const missing = JSON.parse(await readFile(join(source.directory, 'supplement/reports', id + '.json'), 'utf8'));
  expect(missing.captures.find((item: { stage: string }) => item.stage === 'wire_final')).toMatchObject({ recordedStatus: 'complete', bodyStorage: 'missing' });
  expect((await report(source, id)).captures.find(item => item.stage === 'wire_final')!.bodyStorage).toBe('present');
});

test('多页、旧排队请求晚失败、并行采集与重复扫描不丢失或覆盖', async () => {
  const source = await fixture(); source.save({ ...incidentRow('old-pending', 'queued'), finishedAt: null });
  for (let index = 0; index < 107; index++) source.save(incidentRow('request-' + String(index).padStart(3, '0')));
  const one = await collector(source), two = await collector(source);
  await Promise.all([one.collect(), two.collect()]);
  expect(await readdir(join(source.directory, 'incidents/reports'))).toHaveLength(107);
  const before = await readFile(join(source.directory, 'incidents/reports/request-000.json'), 'utf8');
  source.save(incidentRow('old-pending', 'stream_error'));
  await one.collect(); await one.collect();
  expect((await report(source, 'old-pending')).request.state).toBe('stream_error');
  expect(await readdir(join(source.directory, 'incidents/reports'))).toHaveLength(108);
  expect(await readFile(join(source.directory, 'incidents/reports/request-000.json'), 'utf8')).toBe(before);
  expect(one.status().completedCycles).toBeGreaterThanOrEqual(3);
});

test('两个运行的相同请求 ID 不串；运行元数据冲突时拒绝拼接', async () => {
  const a = await fixture('run-a'), b = await fixture('run-b');
  a.save(incidentRow('same-id', 'http_error')); b.save(incidentRow('same-id', 'stream_error'));
  const ca = await collector(a), cb = await collector(b); await Promise.all([ca.collect(), cb.collect()]);
  expect(await report(a, 'same-id')).toMatchObject({ runId: 'run-a', request: { state: 'http_error' } });
  expect(await report(b, 'same-id')).toMatchObject({ runId: 'run-b', request: { state: 'stream_error' } });
  const original = await readFile(join(a.directory, 'incidents/reports/same-id.json'), 'utf8');
  await writeFile(join(a.directory, 'ledger.json'), JSON.stringify({ schemaVersion: 1, mode: 'manual', runId: 'run-b', reservations: [] }));
  expect((await ca.collect()).codes).toContain('RUN_MISMATCH');
  await expect(PoolIncidentCollector.open({ runId: 'run-a', directory: a.directory, output: join(a.directory, 'wrong-run') })).rejects.toThrow('RUN_MISMATCH');
  expect(await readFile(join(a.directory, 'incidents/reports/same-id.json'), 'utf8')).toBe(original);
});

test('旧账本、缺失来源、损坏与超限字段都显式未知，不补造诊断', async () => {
  const source = await fixture(); source.save(incidentRow('legacy'));
  await source.ledger([{ requestId: 'legacy', attempted: true, localStatus: 502, upstreamStatus: null, outcome: 'error' }]);
  const reader = await collector(source); await reader.collect('legacy');
  expect((await report(source, 'legacy')).transport.phase).toBe('unknown');
  source.save(incidentRow('missing-ledger')); await rm(join(source.directory, 'ledger.json'));
  expect((await reader.collect('missing-ledger')).codes).toContain('SOURCE_MISSING');
  expect((await report(source, 'missing-ledger')).forwarding.sourceState).toBe('unavailable');
  source.save(incidentRow('invalid-ledger')); await writeFile(join(source.directory, 'ledger.json'), '{invalid-secret-canary');
  expect((await reader.collect('invalid-ledger')).codes).toContain('SOURCE_INVALID');
  expect(JSON.stringify(await report(source, 'invalid-ledger'))).not.toContain('invalid-secret-canary');
  source.save(incidentRow('oversize-ledger'));
  const file = await open(join(source.directory, 'ledger.json'), 'w'); await file.truncate(32 * 1024 * 1024 + 1); await file.close();
  expect((await reader.collect('oversize-ledger')).codes).toContain('SOURCE_OVERSIZE');
  expect((await report(source, 'oversize-ledger')).forwarding.attempted).toBeNull();
  source.save(incidentRow('oversize-row'));
  source.db.query('UPDATE requests SET payload=? WHERE id=?').run('x'.repeat(1024 * 1024 + 1), 'oversize-row');
  expect((await reader.collect('oversize-row')).codes).toContain('SOURCE_OVERSIZE');
});

test('重复预留、坏捕获和正文索引越界不采纳其它请求或私有文件', async () => {
  const source = await fixture();
  const captures = INCIDENT_STAGES.map(incidentCapture);
  captures[3]!.storedBytes = 10;
  source.save(incidentRow('conflict'), captures, { wire_final: '../../ready.json' });
  await source.ledger([{ requestId: 'conflict', attempted: true }, { requestId: 'conflict', attempted: false }]);
  source.db.query('UPDATE captures SET payload=? WHERE request_id=? AND stage=?').run('{private-corruption', 'conflict', 'cc_prepared');
  const reader = await collector(source); await reader.collect();
  const value = await report(source, 'conflict');
  expect(value.forwarding).toMatchObject({ sourceState: 'conflict', attempted: null });
  expect(value.captures.find(item => item.stage === 'wire_final')!.bodyStorage).toBe('unknown');
  expect(value.captures.find(item => item.stage === 'cc_prepared')!.recordedStatus).toBe('unknown');
  expect(JSON.stringify(value)).not.toContain('private-corruption');
});

test('已有坏报告、外轮状态、新输出冲突和符号链接均不覆盖', async () => {
  const source = await fixture(); source.save(incidentRow('bad-report'));
  const reader = await collector(source), bad = '{private-existing';
  await writeFile(join(source.directory, 'incidents/bad-report.json'), bad);
  expect((await reader.collect()).codes).toContain('REPORT_CONFLICT');
  expect(await readFile(join(source.directory, 'incidents/bad-report.json'), 'utf8')).toBe(bad);
  const statusBefore = await readFile(join(source.directory, 'incidents/status.json'), 'utf8');
  await expect(PoolIncidentCollector.open({ runId: source.runId, directory: source.directory, output: join(source.directory, 'incidents') })).rejects.toThrow();
  expect(await readFile(join(source.directory, 'incidents/status.json'), 'utf8')).toBe(statusBefore);
  const target = join(source.directory, 'link-target'); await mkdir(target, { mode: 0o700 });
  await symlink(target, join(source.directory, 'linked'));
  await expect(PoolIncidentCollector.open({ runId: source.runId, directory: source.directory, output: join(source.directory, 'linked') })).rejects.toThrow();
  expect(await readdir(target)).toEqual([]);
  await reader.close(false);
  const foreign = JSON.stringify({ schemaVersion: 1, runId: 'foreign' });
  await writeFile(join(source.directory, 'incidents/status.json'), foreign);
  await expect(PoolIncidentCollector.open({ runId: source.runId, directory: source.directory })).rejects.toThrow('REPORT_CONFLICT');
  expect(await readFile(join(source.directory, 'incidents/status.json'), 'utf8')).toBe(foreign);
});

test('源锁定与输出不可用只产生固定诊断，解锁后可补采', async () => {
  const source = await fixture(); source.save(incidentRow('locked'));
  source.db.exec('PRAGMA journal_mode=DELETE');
  const reader = await collector(source);
  source.db.exec('BEGIN EXCLUSIVE');
  try { expect((await reader.collect()).codes).toContain('SOURCE_BUSY'); }
  finally { source.db.exec('ROLLBACK'); }
  expect((await reader.collect()).written).toBe(1);
  source.save(incidentRow('write-failure'));
  const original = join(source.directory, 'incidents');
  await rm(original, { recursive: true }); await writeFile(original, 'private-output-canary');
  const status = await reader.collect('write-failure');
  expect(status.codes).toContain('REPORT_WRITE_FAILED');
  expect(JSON.stringify(status)).not.toContain('private-output-canary');
  expect(await readFile(original, 'utf8')).toBe('private-output-canary');
});

test('后台日志关闭与采集缺口可见，关闭后定时器和状态写入停止', async () => {
  const source = await fixture(); let reads = 0;
  const reader = await PoolIncidentCollector.open({ runId: source.runId, directory: source.directory, getLogStatus: () => { reads++; return { mode: 'off', captureErrorPresent: true }; }, onDiagnostic() { throw new Error('private-callback-canary'); } }); collectors.push(reader);
  reader.start(); await reader.close();
  const status = JSON.parse(await readFile(join(source.directory, 'incidents/status.json'), 'utf8'));
  expect(status.phase).toBe('stopped'); expect(status.codes).toContain('LOG_CAPTURE_DISABLED'); expect(status.codes).toContain('LOG_CAPTURE_GAP');
  const before = reads, stamp = (await lstat(join(source.directory, 'incidents/status.json'))).mtimeMs;
  await Bun.sleep(2200);
  expect(reads).toBe(before); expect((await lstat(join(source.directory, 'incidents/status.json'))).mtimeMs).toBe(stamp);
});

test('一次性 CLI 不启动服务，支持新目录补采，拒绝未知参数及非终态', async () => {
  const source = await fixture(), body = 'cli-failure-wire_final-1-1.txt';
  const captures = INCIDENT_STAGES.map(incidentCapture); captures[3]!.storedBytes = 9;
  await writeFile(join(source.directory, 'data/bodies', body), 'body-only');
  source.save(incidentRow('cli-failure'), captures, { wire_final: body }); source.save(incidentRow('cli-running', 'running'));
  const before = await sourceSnapshot(source);
  const trace = join(source.directory, 'open-proof.txt'), strace = Bun.which('strace');
  const invoke = async (args: string[], inspect = false) => {
    const command = [process.execPath, resolve('scripts/collect-pool-incidents.ts'), ...args];
    const child = Bun.spawn(inspect && strace ? [strace, '-f', '-e', 'trace=openat,openat2', '-o', trace, ...command] : command, { env: { PATH: process.env.PATH ?? '/usr/bin:/bin', HOME: '/tmp', LANG: 'C.UTF-8' }, stdout: 'pipe', stderr: 'pipe' });
    const output = Promise.all([new Response(child.stdout).text(), new Response(child.stderr).text()]);
    const code = await child.exited, [stdout, stderr] = await output; return { code, stdout, stderr };
  };
  const args = ['--run', source.runId, '--run-dir', source.directory];
  const valid = await invoke([...args, '--request-id', 'cli-failure'], true);
  expect(valid.code).toBe(0); expect(JSON.parse(valid.stdout).written).toBe(1); expect(valid.stderr).toBe('');
  if (strace) { const observed = await readFile(trace, 'utf8'); expect(observed).toContain('data/logs.sqlite'); expect(observed).not.toContain(join(source.directory, 'data/bodies', body)); }
  const supplement = await invoke([...args, '--request-id', 'cli-failure', '--output', join(source.directory, 'cli-supplement')]);
  expect(supplement.code).toBe(0);
  expect(await sourceSnapshot(source)).toBe(before);
  const invalid = await invoke([...args, '--unknown', 'private-cli-canary']);
  expect(invalid.code).toBe(1); expect(invalid.stderr).toBe('本地池取证失败：SOURCE_INVALID\n'); expect(invalid.stdout).not.toContain('private-cli-canary');
  const pending = await invoke([...args, '--request-id', 'cli-running']);
  expect(pending.code).toBe(1); expect(JSON.parse(pending.stdout).codes).toContain('REQUEST_NOT_TERMINAL');
});

test('CHK-001：合法保留字请求 ID 与状态隔离，旧平铺报告只读复用', async () => {
  const source = await fixture();
  for (const id of ['status', 'reports', 'legacy-report']) source.save(incidentRow(id));
  const reader = await collector(source);
  expect((await reader.collect()).written).toBe(3);
  expect((await report(source, 'status')).requestId).toBe('status');
  expect((await report(source, 'reports')).requestId).toBe('reports');
  const status = JSON.parse(await readFile(join(source.directory, 'incidents/status.json'), 'utf8'));
  expect(status.runId).toBe(source.runId); expect(status.requestId).toBeUndefined();
  const legacyPath = join(source.directory, 'incidents/legacy-report.json');
  await rename(join(source.directory, 'incidents/reports/legacy-report.json'), legacyPath);
  const before = await readFile(legacyPath, 'utf8');
  await reader.close(false);
  const reopened = await collector(source), result = await reopened.collect();
  expect(result).toMatchObject({ written: 0, existing: 3, codes: [] });
  expect(await readFile(legacyPath, 'utf8')).toBe(before);
  expect(await Bun.file(join(source.directory, 'incidents/reports/legacy-report.json')).exists()).toBe(false);
});

test('FBK-001：关闭累计首中尾页的不同故障，修复来源后下一轮恢复正常', async () => {
  const source = await fixture();
  for (let index = 0; index < 207; index++) source.save(incidentRow('case-' + String(index).padStart(3, '0')));
  const reader = await collector(source), brokenPath = join(source.directory, 'incidents/reports/case-000.json');
  await writeFile(brokenPath, '{broken');
  source.db.query('UPDATE requests SET payload=? WHERE id=?').run('x'.repeat(1024 * 1024 + 1), 'case-103');
  source.db.query('UPDATE requests SET payload=? WHERE id=?').run('{}', 'case-206');
  await reader.close();
  const status = JSON.parse(await readFile(join(source.directory, 'incidents/status.json'), 'utf8'));
  expect(status.phase).toBe('stopped'); expect(status.written).toBe(204);
  expect(status.codes).toContain('REPORT_CONFLICT'); expect(status.codes).toContain('SOURCE_OVERSIZE'); expect(status.codes).toContain('SOURCE_INVALID');
  expect(await readFile(brokenPath, 'utf8')).toBe('{broken');
  await rm(brokenPath); source.save(incidentRow('case-103')); source.save(incidentRow('case-206'));
  const reopened = await collector(source);
  expect((await reopened.collect()).codes).toEqual([]);
  expect(reopened.status().written).toBe(3);
  await reopened.close();
  expect(JSON.parse(await readFile(join(source.directory, 'incidents/status.json'), 'utf8'))).toMatchObject({ phase: 'stopped', codes: [] });
});

test('FBK-001：末页成功不清除首、次页故障', async () => {
  const source = await fixture();
  for (let index = 0; index < 207; index++) source.save(incidentRow('case-' + String(index).padStart(3, '0')));
  const reader = await collector(source);
  await writeFile(join(source.directory, 'incidents/reports/case-000.json'), '{broken');
  source.db.query('UPDATE requests SET payload=? WHERE id=?').run('{}', 'case-103');
  await reader.close();
  const status = JSON.parse(await readFile(join(source.directory, 'incidents/status.json'), 'utf8'));
  expect(status).toMatchObject({ phase: 'stopped', written: 205 });
  expect(status.codes).toContain('REPORT_CONFLICT'); expect(status.codes).toContain('SOURCE_INVALID');
});

test('FBK-002：完整校验坏报告且不覆盖，合法缺证与摘要报告仍可去重', async () => {
  const source = await fixture(); source.save(incidentRow('template'));
  const reader = await collector(source); await reader.collect('template');
  const template = await report(source, 'template');
  const corruptions: [string, (value: PoolIncidentReport) => Record<string, unknown>][] = [
    ['transport-empty', value => ({ ...value, transport: {} })],
    ['transport-negative', value => ({ ...value, transport: { ...value.transport, connectionBytesRead: -1 } })],
    ['captures-null', value => ({ ...value, captures: [null, null, null, null, null] })],
    ['capture-missing', value => ({ ...value, captures: value.captures.filter(item => item.stage !== 'wire_final') })],
    ['capture-extra', value => ({ ...value, captures: value.captures.map(item => ({ ...item, privateField: 'private-report-canary' })) })],
    ['request-incomplete', value => ({ ...value, request: { state: 'http_error' } })],
    ['forwarding-code', value => ({ ...value, forwarding: { ...value.forwarding, failureCode: 'private-report-canary' } })],
    ['extra-root', value => ({ ...value, privateField: 'private-report-canary' })],
    ['gap-unknown', value => ({ ...value, evidenceGaps: ['private-report-canary'] })],
    ['interpretation-invalid', value => ({ ...value, interpretation: { ...value.interpretation, tls: 'private-report-canary' } })],
    ['correlation-missing', value => ({ ...value, correlations: [] })],
    ['correlation-duplicate', value => ({ ...value, correlations: [...value.correlations, value.correlations[0]] })],
    ['correlation-attempt', value => ({ ...value, correlations: value.correlations.map(item => item.stage === 'wire_final' ? { ...item, attempt: 999 } : item) })],
    ['interpretation-missing', ({ interpretation, ...value }) => value],
  ];
  for (const [index, [id, corrupt]] of corruptions.entries()) {
    source.save(incidentRow(id));
    const path = join(source.directory, index % 2 ? 'incidents' : 'incidents/reports', id + '.json');
    const original = JSON.stringify({ ...corrupt(structuredClone(template)), requestId: id });
    await writeFile(path, original);
    const result = await reader.collect(id);
    expect(result.codes).toContain('REPORT_CONFLICT'); expect(result.written).toBe(1);
    expect(JSON.stringify(result)).not.toContain('private-report-canary');
    expect(await readFile(path, 'utf8')).toBe(original);
  }
  source.save({ ...incidentRow('partial', 'incomplete'), mode: 'summary', finishedAt: null }, []);
  expect((await reader.collect('partial')).written).toBe(2);
  const partial = await report(source, 'partial');
  expect(partial.request.finishedAt).toBeNull(); expect(partial.captures.every(item => item.attempt === null && item.recordedStatus === 'unknown')).toBe(true);
  expect(partial.transport.phase).toBe('unknown');
  const repeated = await reader.collect('partial');
  expect(repeated.codes).toEqual([]); expect(repeated.existing).toBeGreaterThan(0); expect(repeated.written).toBe(2);
});
