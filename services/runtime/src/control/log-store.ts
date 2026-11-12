import { Database } from 'bun:sqlite';
import { mkdir, readFile } from 'node:fs/promises';
import { join } from 'node:path';
import type { AgentAssociation, AgentAssociationEvidence, AgentLaunchEvidence, LogFilters, RequestContext, RequestDetail, RequestRow } from '../shared/contracts';
import type { LogSnapshot, LogWriterConfig } from './log-schema';
import { isObject } from '../shared/errors';
import { AGENT_EVIDENCE_LIMIT, isAgentLaunches, resolveAgentAssociation } from '../shared/request-attribution';

/** 非阻塞日志存储，写入与清理运行在独立线程，查询使用 WAL 只读连接。 */
export class LogStore {
  private readonly worker: Worker;
  private db!: Database;
  private sequence = 0;
  private readonly pending = new Map<number, number>();
  private readonly pendingIds = new Map<number, string>();
  private pendingBytes = 0;
  private readonly failedIds = new Set<string>();
  private readonly waiters = new Set<() => void>();
  private closed = false;
  private closeResolve: (() => void) | null = null;
  public error: string | null = null;

  /** 创建异步日志写入端。
   * @param config 持久化配置。
   */
  constructor(private readonly config: LogWriterConfig) {
    this.worker = new Worker(new URL('./log-writer.ts', import.meta.url).href, { type: 'module' });
  }

  /** 等待表结构就绪，不访问官方程序。
   * @return 日志库已可以查询。
   */
  async open(): Promise<void> {
    await mkdir(this.config.bodyDir, { recursive: true, mode: 0o700 });
    await new Promise<void>((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error('日志线程初始化超时')), 5000);
      let initialized = false;
      this.worker.onerror = () => { this.error = '日志线程异常'; clearTimeout(timeout); reject(new Error(this.error)); this.releaseWaiters(); };
      this.worker.onmessage = (message: MessageEvent<unknown>) => {
        const value = message.data;
        if (!isObject(value)) return;
        if (value.type === 'ready') {
          initialized = true;
          clearTimeout(timeout);
          this.db = new Database(this.config.dbPath, { readonly: true, strict: true });
          this.db.exec('PRAGMA busy_timeout = 1000');
          resolve();
        } else if (value.type === 'ack' || value.type === 'failed') {
          const seq = Number(value.sequence);
          this.pendingBytes -= this.pending.get(seq) ?? 0;
          this.pending.delete(seq);
          if (value.type === 'failed') {
            this.error = '日志写入失败';
            const id = this.pendingIds.get(seq);
            if (id) this.failedIds.add(id);
            if (!initialized) { clearTimeout(timeout); reject(new Error(this.error)); this.worker.terminate(); }
          }
          this.pendingIds.delete(seq);
          if (this.pending.size === 0) this.releaseWaiters();
        } else if (value.type === 'closed') {
          this.closeResolve?.();
        }
      };
      this.worker.postMessage({ type: 'init', config: this.config });
    });
  }

  private releaseWaiters(): void {
    for (const resolve of this.waiters) resolve();
    this.waiters.clear();
  }

  /** 有界提交快照，失败只标记采集缺口，不阻塞模型响应。
   * @param snapshot 已完成脱敏的数据。
   * @return 是否交给写入线程。
   */
  record(snapshot: LogSnapshot): boolean {
    const bytes = Buffer.byteLength(JSON.stringify(snapshot));
    if (this.closed || this.error || this.pendingBytes + bytes > 16 * 1024 * 1024 || this.pending.size >= 64) {
      this.failedIds.add(snapshot.request.id);
      this.error = this.error ?? '日志队列达到上限，部分采集未保存';
      return false;
    }
    const sequence = ++this.sequence;
    this.pending.set(sequence, bytes);
    this.pendingIds.set(sequence, snapshot.request.id);
    this.pendingBytes += bytes;
    try { this.worker.postMessage({ type: 'save', sequence, snapshot }); }
    catch {
      this.pendingBytes -= bytes; this.pending.delete(sequence); this.pendingIds.delete(sequence);
      this.failedIds.add(snapshot.request.id); this.error = '日志线程无法接收数据'; this.releaseWaiters();
      return false;
    }
    return true;
  }

  /** 判断请求标识是否已经持久保存。
   * @param id 请求标识。
   * @return 是否存在。
   */
  exists(id: string): boolean {
    return this.db.query('SELECT 1 FROM requests WHERE id=?').get(id) !== null;
  }

  /** 查询持久列表，不执行任何运行时动作。
   * @param filters 已限制长度与数量的过滤条件。
   * @return 时间倒序的列表和匹配总数。
   */
  list(filters: LogFilters = {}): { rows: RequestRow[]; total: number } {
    const clauses: string[] = [];
    const values: (string | number)[] = [];
    for (const [field, value] of [['model', filters.model], ['state', filters.state], ['request_class', filters.requestClass], ['session_id', filters.sessionId]] as const) {
      if (value) { clauses.push(field + ' = ?'); values.push(value); }
    }
    if (filters.requestId) { clauses.push('id LIKE ? ESCAPE CHAR(92)'); values.push('%' + filters.requestId.replace(/[\\%_]/g, '\\$&') + '%'); }
    if (filters.since) { clauses.push('created_at >= ?'); values.push(filters.since); }
    if (filters.until) { clauses.push('created_at <= ?'); values.push(filters.until); }
    const where = clauses.length ? ' WHERE ' + clauses.join(' AND ') : '';
    const total = this.db.query<{ count: number }, (string | number)[]>('SELECT COUNT(*) AS count FROM requests' + where).get(...values)?.count ?? 0;
    const limit = Math.max(1, Math.min(100, filters.limit ?? 50));
    const offset = Math.max(0, filters.offset ?? 0);
    const rows = this.db.query<{ payload: string }, (string | number)[]>('SELECT payload FROM requests' + where + ' ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?').all(...values, limit, offset).map(row => JSON.parse(row.payload) as RequestRow);
    for (const row of rows) if (this.failedIds.has(row.id)) row.captureError = this.error;
    return { rows, total };
  }

  private association(request: RequestRow, context: RequestContext): AgentAssociation {
    const candidates: (AgentLaunchEvidence & AgentAssociationEvidence)[] = [];
    let incomplete = this.failedIds.has(request.id) || this.error !== null;
    try {
      incomplete ||= this.db.query(`SELECT 1 FROM requests WHERE session_id=? AND json_type(payload,'$.agentLaunches') IS NOT NULL AND
        (COALESCE(json_extract(payload,'$.agentLaunches.state'),'')!='complete' OR COALESCE(json_type(payload,'$.agentLaunches.links'),'')!='array') LIMIT 1`).get(context.sessionId) !== null;
      // 先按声明去重再限制数量，长会话反复携带相同历史不会耗尽关联额度。
      // SQLite 的单个 MIN 聚合会从该证据请求所在行取得 link，证据定位与内容保持同源。
      const rows = this.db.query<{ id: string; link: string }, [string, string, number]>(`SELECT MIN(r.id) AS id,e.value AS link FROM requests r,json_each(r.payload,'$.agentLaunches.links') e
        WHERE r.session_id=? AND json_extract(e.value,'$.childAgentId')=?
        GROUP BY json_extract(e.value,'$.parentAgentId'),json_extract(e.value,'$.agentType'),json_extract(e.value,'$.toolUseId') LIMIT ?`).all(context.sessionId, context.agentId ?? '', AGENT_EVIDENCE_LIMIT + 1);
      incomplete ||= rows.length > AGENT_EVIDENCE_LIMIT;
      for (const row of rows.slice(0, AGENT_EVIDENCE_LIMIT)) {
        const value: unknown = { state: 'complete', links: [JSON.parse(row.link)] };
        if (!isAgentLaunches(value)) { incomplete = true; continue; }
        incomplete ||= this.failedIds.has(row.id);
        candidates.push({ ...value.links[0]!, requestId: row.id });
      }
    } catch { incomplete = true; }
    return resolveAgentAssociation(context, candidates, incomplete);
  }

  /** 读取一个请求及独立正文文件。
   * @param id 请求 ID。
   * @return 详情，记录不存在时返回 null。
   */
  async detail(id: string): Promise<RequestDetail | null> {
    // WAL 允许查询期间提交新快照；把元数据读在同一事务内，避免跨代拼接。
    const snapshot = this.db.transaction(() => {
      const row = this.db.query<{ payload: string; context_json: string; decisions_json: string }, [string]>('SELECT payload,context_json,decisions_json FROM requests WHERE id=?').get(id);
      if (!row) return null;
      const request = JSON.parse(row.payload) as RequestRow;
      if (this.failedIds.has(id)) request.captureError = this.error;
      const captures = this.db.query<{ payload: string; body_file: string | null }, [string]>('SELECT payload,body_file FROM captures WHERE request_id=? ORDER BY rowid').all(id);
      const context = JSON.parse(row.context_json) as RequestContext | null;
      return { request, context, decisions: JSON.parse(row.decisions_json), captures,
        ...(context && (context.agentKind === 'subagent' || context.agentKind === 'teammate') ? { agentAssociation: this.association(request, context) } : {}),
      };
    })();
    if (!snapshot) return null;
    // 文件 IO 在事务外等待，避免把异步读取变成数据库长事务。
    const records = await Promise.all(snapshot.captures.map(async capture => {
      const parsed = JSON.parse(capture.payload);
      if (capture.body_file) {
        try { parsed.text = await readFile(join(this.config.bodyDir, capture.body_file), 'utf8'); }
        catch { parsed.status = 'failed'; parsed.note = '原文文件未能读取'; }
      }
      return parsed;
    }));
    return { ...snapshot, captures: records };
  }

  /** 等待已提交日志，用于有序关闭和验收，不在响应热路径调用。
   * @return 已确认队列排空或故障。
   */
  async flush(): Promise<void> {
    if (this.pending.size === 0 || this.error) return;
    await new Promise<void>(resolve => {
      const done = (): void => { clearTimeout(timer); this.waiters.delete(done); resolve(); };
      const timer = setTimeout(done, 5000);
      this.waiters.add(done);
    });
  }

  /** 关闭日志线程及查询连接。
   * @return 资源释放完成。
   */
  async close(): Promise<void> {
    await this.flush();
    this.closed = true;
    this.db?.close();
    if (!this.error) await new Promise<void>(resolve => {
      const done = (): void => { clearTimeout(timer); this.closeResolve = null; resolve(); };
      const timer = setTimeout(done, 2000);
      this.closeResolve = done;
      this.worker.postMessage({ type: 'close' });
    });
    this.worker.terminate();
  }
}
