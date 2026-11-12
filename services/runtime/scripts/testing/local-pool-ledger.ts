import { writeFile, rename } from 'node:fs/promises';
import type { LocalPoolStatus } from '../../src/control/server';
import { BridgeError, isObject } from '../../src/shared/errors';
import { POOL_MODEL, POOL_FAILURE_CODES, decodePoolTransportDiagnostics, type PoolTransportDiagnostics } from './pool-common';

/** 手工运行的预留与结果；不保存正文、地址或凭据。 */
interface Reservation { requestId: string; reservedAt: string; attempted?: boolean; upstreamStatus?: number | null; localStatus?: number; outcome?: string; failureCode?: string; transportDiagnostics?: PoolTransportDiagnostics }

/** 发送前持久预留预算，异常退出后也不能覆盖同一轮账本。 */
export class LocalPoolLedger {
  private readonly reservations: Reservation[] = [];
  /** 绑定显式轮次及其额度。 @param path 排他创建的账本路径。 @param runId 本轮 ID。 @param live 是否真实池。 @param budget 本轮上限，null 表示不限次数。 */
  private constructor(private readonly path: string, private readonly runId: string, private readonly live: boolean, private readonly budget: number | null) {}
  /** 排他创建新轮次。 @param path 账本路径。 @param runId 本轮 ID。 @param live 是否真实池。 @param budget 本轮上限，null 表示不限次数。 @return 新账本，已有文件明确拒绝。 */
  static async create(path: string, runId: string, live: boolean, budget: number | null): Promise<LocalPoolLedger> {
    if (!/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(runId) || (budget !== null && (!Number.isSafeInteger(budget) || budget < 1 || budget > 20))) throw new Error('手工轮次或预算不合法');
    const ledger = new LocalPoolLedger(path, runId, live, budget);
    try { await writeFile(path, ledger.json(), { flag: 'wx', mode: 0o600 }); }
    catch (error) { if (isObject(error) && error.code === 'EEXIST') throw new BridgeError('local_pool_run_exists', '本轮目录已有账本，请保留并显式选择新的运行 ID，不能覆盖重置', 409); throw error; }
    return ledger;
  }
  /** 返回健康接口的只读预算。 @return 预留数为可能发生的实际调用上界。 */
  status(): LocalPoolStatus { return { runId: this.runId, model: POOL_MODEL, live: this.live, budget: this.budget, reserved: this.reservations.length, remaining: this.budget === null ? null : this.budget - this.reservations.length }; }
  private json(): string { return JSON.stringify({ schemaVersion: 1, mode: 'manual', ...this.status(), reservations: this.reservations }, null, 2) + '\n'; }
  private async save(): Promise<void> { await writeFile(this.path + '.tmp', this.json(), { mode: 0o600 }); await rename(this.path + '.tmp', this.path); }
  /** 在允许 Node 发请求前写入预算。 @param requestId 当前请求。 @return 持久化完成才可发送。 */
  async reserve(requestId: string): Promise<void> {
    if (this.budget !== null && this.reservations.length >= this.budget) throw new BridgeError('pool_budget_exhausted', '本次池联调额度已用尽', 429);
    this.reservations.push({ requestId, reservedAt: new Date().toISOString() });
    await this.save();
  }
  /** 记录已预留请求的真实回执，不把本地错误当成池状态。 @param requestId 请求归属。 @param result Node 回执。 @return 账本已更新。 */
  async finish(requestId: string, result: { attempted: boolean; upstreamStatus: number | null; statusCode: number; outcome: string; failureCode?: string; transportDiagnostics?: PoolTransportDiagnostics }): Promise<void> {
    const row = this.reservations.find(item => item.requestId === requestId);
    if (!row) return;
    Object.assign(row, { attempted: result.attempted, upstreamStatus: result.upstreamStatus, localStatus: result.statusCode, outcome: result.outcome });
    if (result.failureCode !== undefined) row.failureCode = POOL_FAILURE_CODES.has(result.failureCode) ? result.failureCode : result.attempted ? 'POOL_FETCH_ERROR' : 'REQUEST_REJECTED';
    if (result.transportDiagnostics !== undefined) row.transportDiagnostics = decodePoolTransportDiagnostics(result.transportDiagnostics);
    await this.save();
  }
}
