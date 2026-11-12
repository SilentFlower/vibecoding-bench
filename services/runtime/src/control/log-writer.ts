import { Database } from 'bun:sqlite';
import { mkdirSync, readdirSync, statSync, unlinkSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import type { LogSnapshot, LogWriterConfig } from './log-schema';
import { createLogSchema } from './log-schema';
import { isObject } from '../shared/errors';

let db: Database;
let config: LogWriterConfig;
let cleanupTimer: ReturnType<typeof setInterval> | undefined;

function removeFile(name: string | null): void {
  if (!name) return;
  try { unlinkSync(join(config.bodyDir, name)); } catch {}
}

function deleteRequest(id: string): void {
  const files = db.query<{ body_file: string | null }, [string]>('SELECT body_file FROM captures WHERE request_id = ?').all(id);
  db.query('DELETE FROM requests WHERE id = ?').run(id);
  for (const file of files) removeFile(file.body_file);
}

function cleanup(): void {
  const cutoff = new Date(Date.now() - config.retainDays * 86400000).toISOString();
  // 请求可能跨过保留期，摘要和正文都必须等终态后才进入回收。
  for (const row of db.query<{ id: string }, [string]>('SELECT id FROM requests WHERE created_at < ? AND state NOT IN ("queued","running")').all(cutoff)) deleteRequest(row.id);
  const debugCutoff = new Date(Date.now() - config.debugRetainDays * 86400000).toISOString();
  const expired = db.query<{ request_id: string; stage: string; attempt: number; body_file: string }, [string]>('SELECT c.request_id,c.stage,c.attempt,c.body_file FROM captures c JOIN requests r ON r.id=c.request_id WHERE r.created_at < ? AND r.state NOT IN ("queued","running") AND c.body_file IS NOT NULL').all(debugCutoff);
  for (const row of expired) {
    const existing = db.query<{ payload: string }, [string, string, number]>('SELECT payload FROM captures WHERE request_id=? AND stage=? AND attempt=?').get(row.request_id, row.stage, row.attempt);
    if (!existing) continue;
    const payload = JSON.parse(existing.payload);
    payload.status = 'unavailable'; payload.storedBytes = 0; payload.note = '原文已过保留期';
    db.query('UPDATE captures SET body_file=NULL,payload=? WHERE request_id=? AND stage=? AND attempt=?').run(JSON.stringify(payload), row.request_id, row.stage, row.attempt);
    removeFile(row.body_file);
  }
  // 总量按保存的正文及 JSON 载荷计数；SQLite 的页和 WAL 另有固定存储开销。
  while (true) {
    const size = db.query<{ bytes: number }, []>('SELECT COALESCE((SELECT SUM(LENGTH(CAST(payload AS BLOB))+LENGTH(CAST(context_json AS BLOB))+LENGTH(CAST(decisions_json AS BLOB))) FROM requests),0)+COALESCE((SELECT SUM(LENGTH(CAST(payload AS BLOB))+json_extract(payload, "$.storedBytes")) FROM captures),0) AS bytes').get()?.bytes ?? 0;
    if (size <= config.maxBytes) break;
    const oldest = db.query<{ id: string }, []>('SELECT id FROM requests WHERE state NOT IN ("queued","running") ORDER BY created_at LIMIT 1').get();
    if (!oldest) break;
    deleteRequest(oldest.id);
  }
  const referenced = new Set(db.query<{ body_file: string }, []>('SELECT body_file FROM captures WHERE body_file IS NOT NULL').all().map(row => row.body_file));
  for (const name of readdirSync(config.bodyDir)) {
    if (!referenced.has(name) && Date.now() - statSync(join(config.bodyDir, name)).mtimeMs > 30000) removeFile(name);
  }
  db.exec('PRAGMA wal_checkpoint(PASSIVE); PRAGMA incremental_vacuum(64);');
}

function save(snapshot: LogSnapshot, sequence: number): void {
  const row = snapshot.request;
  // 正文先写到本轮唯一文件；索引尚未发布时，读者继续读取旧快照。
  const changes = snapshot.captures.flatMap(capture => {
    const previous = db.query<{ payload: string; body_file: string | null }, [string, string, number]>('SELECT payload,body_file FROM captures WHERE request_id=? AND stage=? AND attempt=?').get(row.id, capture.stage, capture.attempt);
    const payload = JSON.stringify({ ...capture, text: null });
    if (previous?.payload === payload) return [];
    let file: string | null = null;
    if (capture.text !== null) {
      file = row.id + '-' + capture.stage + '-' + capture.attempt + '-' + sequence + '.txt';
      writeFileSync(join(config.bodyDir, file), capture.text, { mode: 0o600 });
    }
    return [{ stage: capture.stage, attempt: capture.attempt, payload, file }];
  });
  // 请求终态和全部阶段索引必须一起发布；阶段失败时不能留下成功请求行。
  db.transaction(() => {
    db.query('INSERT INTO requests VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET state=excluded.state,payload=excluded.payload,context_json=excluded.context_json,decisions_json=excluded.decisions_json').run(row.id, row.createdAt, row.model, row.state, row.requestClass, row.sessionId, JSON.stringify(row), JSON.stringify(snapshot.context), JSON.stringify(snapshot.decisions));
    for (const change of changes) {
      db.query('INSERT INTO captures VALUES (?,?,?,?,?) ON CONFLICT(request_id,stage,attempt) DO UPDATE SET payload=excluded.payload,body_file=excluded.body_file').run(row.id, change.stage, change.attempt, change.payload, change.file);
    }
  })();
  // 回滚后的新文件及不再引用的旧文件均延后清理，保护已取得旧索引的读者。
  cleanup();
}

self.onmessage = (message: MessageEvent<unknown>) => {
  const value = message.data;
  if (!isObject(value)) return;
  try {
    if (value.type === 'init') {
      config = value.config as unknown as LogWriterConfig;
      mkdirSync(config.bodyDir, { recursive: true, mode: 0o700 });
      db = new Database(config.dbPath, { create: true, strict: true });
      createLogSchema(db);
      // 未完成的历史记录必须显式成为未知终态，不能在重启后一直显示正在执行。
      db.query('UPDATE requests SET state="incomplete",payload=json_set(payload,"$.state","incomplete","$.captureError","控制进程结束前没有保存完整终态") WHERE state IN ("queued","running")').run();
      cleanup();
      cleanupTimer = setInterval(() => {
        try { cleanup(); } catch { postMessage({ type: 'failed', error: '日志清理失败' }); }
      }, 60000);
      postMessage({ type: 'ready' });
    } else if (value.type === 'save') {
      save(value.snapshot as unknown as LogSnapshot, Number(value.sequence));
      postMessage({ type: 'ack', sequence: value.sequence });
    } else if (value.type === 'close') {
      clearInterval(cleanupTimer);
      db.exec('PRAGMA wal_checkpoint(TRUNCATE)');
      db.close();
      postMessage({ type: 'closed' });
    }
  } catch {
    postMessage({ type: 'failed', sequence: value.sequence, error: '日志写入失败，当前响应不重放' });
  }
};
