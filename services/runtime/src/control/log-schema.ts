import { Database } from 'bun:sqlite';
import type { CaptureRecord, HeaderDecision, RequestContext, RequestRow } from '../shared/contracts';

/** 控制进程交给独立日志线程的快照。 */
export interface LogSnapshot {
  request: RequestRow;
  context: RequestContext | null;
  decisions: HeaderDecision[];
  captures: CaptureRecord[];
}

/** 日志线程固定配置，不包含运行时凭据。 */
export interface LogWriterConfig {
  dbPath: string;
  bodyDir: string;
  retainDays: number;
  debugRetainDays: number;
  maxBytes: number;
}

/** 创建日志表及读取索引，不由外部请求提供 SQL。
 * @param db 本地数据库。
 * @return 表结构就绪。
 */
export function createLogSchema(db: Database): void {
  db.exec('PRAGMA auto_vacuum = INCREMENTAL; PRAGMA journal_mode = WAL; PRAGMA foreign_keys = ON; PRAGMA busy_timeout = 3000;');
  db.exec('CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, model TEXT NOT NULL, state TEXT NOT NULL, request_class TEXT NOT NULL, session_id TEXT NOT NULL, payload TEXT NOT NULL, context_json TEXT NOT NULL, decisions_json TEXT NOT NULL); CREATE INDEX IF NOT EXISTS requests_time ON requests(created_at DESC); CREATE INDEX IF NOT EXISTS requests_session ON requests(session_id); CREATE TABLE IF NOT EXISTS captures (request_id TEXT NOT NULL REFERENCES requests(id) ON DELETE CASCADE, stage TEXT NOT NULL, attempt INTEGER NOT NULL, payload TEXT NOT NULL, body_file TEXT, PRIMARY KEY(request_id, stage, attempt));');
}
