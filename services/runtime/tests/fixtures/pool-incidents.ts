import { Database } from 'bun:sqlite';
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import type { CaptureRecord, CaptureStage, RequestRow, RequestState } from '../../src/shared/contracts';
import { createLogSchema } from '../../src/control/log-schema';

export const INCIDENT_TIME = '2026-11-07T00:00:00.000Z';
export const INCIDENT_STAGES: CaptureStage[] = ['ingress', 'header_policy', 'cc_prepared', 'wire_final', 'upstream_response'];

/** 生成完整合成请求行。 @param id 请求 ID。 @param state 请求状态。 @return 与真实表合同一致的无账号夹具。 */
export function incidentRow(id: string, state: RequestState = 'http_error'): RequestRow {
  return { id, state, createdAt: INCIDENT_TIME, finishedAt: INCIDENT_TIME, model: 'fixture', requestClass: 'main', sessionId: 'fixture-session', promptId: 'fixture-prompt', agentId: null, parentAgentId: null, httpStatus: 502, durationMs: 1, headersMs: null, firstOutputMs: null, mode: 'debug', engine: 'fixture', binarySha256: null, error: null, captureError: null };
}

/** 生成不需要保存正文的合成阶段。 @param stage 已知采集阶段。 @return 完整元数据。 */
export function incidentCapture(stage: CaptureStage): CaptureRecord {
  const source = stage === 'wire_final' ? 'local_pool_node_tls_receiver' : stage === 'upstream_response' ? 'native_response' : stage === 'cc_prepared' ? 'claude_code_293_cli_prepared' : stage === 'ingress' ? 'http_ingress' : 'header_policy';
  return { stage, attempt: 1, capturedAt: INCIDENT_TIME, source, representation: stage === 'wire_final' ? 'http_entity_body_after_native_transport' : stage === 'upstream_response' ? 'response_logical_bytes' : 'json', status: 'complete', observedBytes: 9, storedBytes: 0, sha256: 'a'.repeat(64), text: null, headers: [], note: null };
}

/** 合成存储的控制端，只供离线测试写入自己的目录。 */
export interface IncidentFixture {
  directory: string; runId: string; db: Database;
  /** 保存合成快照。 @param row 请求。 @param captures 阶段。 @param files 可选正文索引。 @return 无。 */
  save(row: RequestRow, captures?: CaptureRecord[], files?: Partial<Record<CaptureStage, string>>): void;
  /** 写入合成账本。 @param reservations 合成预留。 @return 已持久化。 */
  ledger(reservations: unknown[]): Promise<void>;
  /** 清理测试自有资源。 @return 已清理。 */
  close(): Promise<void>;
}

/** 创建真实表结构的临时离线夹具。 @param runId 合成运行轮次。 @return 仅测试拥有的可写源。 */
export async function incidentFixture(runId = 'incident-test'): Promise<IncidentFixture> {
  const directory = await mkdtemp(join(tmpdir(), 'ccrb-incidents-'));
  await mkdir(join(directory, 'data/bodies'), { recursive: true, mode: 0o700 });
  const db = new Database(join(directory, 'data/logs.sqlite'));
  createLogSchema(db);
  await writeFile(join(directory, 'ready.json'), JSON.stringify({ runId, startedAt: INCIDENT_TIME }), { mode: 0o600 });
  const fixture: IncidentFixture = {
    directory, runId, db,
    save(row, captures = INCIDENT_STAGES.map(incidentCapture), files = {}) {
      db.query('INSERT INTO requests VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET state=excluded.state,payload=excluded.payload').run(row.id, row.createdAt, row.model, row.state, row.requestClass, row.sessionId, JSON.stringify(row), 'null', '[]');
      for (const capture of captures) db.query('INSERT INTO captures VALUES (?,?,?,?,?) ON CONFLICT(request_id,stage,attempt) DO UPDATE SET payload=excluded.payload,body_file=excluded.body_file').run(row.id, capture.stage, capture.attempt, JSON.stringify({ ...capture, text: null }), files[capture.stage] ?? null);
    },
    async ledger(reservations) { await writeFile(join(directory, 'ledger.json'), JSON.stringify({ schemaVersion: 1, mode: 'manual', runId, model: 'deepseek-flash', live: false, budget: null, remaining: null, reserved: reservations.length, reservations }), { mode: 0o600 }); },
    async close() { db.close(); await rm(directory, { recursive: true, force: true }); },
  };
  await fixture.ledger([]);
  return fixture;
}
