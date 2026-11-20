import type { SystemUpdateOperation } from '../api';

/** 更新阶段的中文名称；未登记的阶段由调用方显示原值。 */
export const UPDATE_PHASE_LABELS: Record<string, string> = {
  snapshotting: '保存数据库快照', migrating: '执行数据库迁移', restoring_data: '正在恢复数据库',
  preparing: '下载与校验', prepared: '待重启', draining: '等待在途完成', switching: '切换平台服务',
  verifying: '验证新版本', committing: '保存安装结果', cleaning: '回收旧制品', succeeded: '更新完成',
  succeeded_cleanup_pending: '更新完成，清理待重试', restoring: '正在恢复原版本', restored: '已恢复原版本',
  failed: '本次更新失败', cancelled: '本次更新已取消', reconcile: '等待恢复与对账',
};

/** 结局阶段不进入步骤列表，由状态标签与提示条呈现。 */
export const UPDATE_OUTCOMES = new Set(['succeeded', 'succeeded_cleanup_pending', 'failed', 'cancelled', 'restored', 'reconcile', 'prepared']);

/** 步骤表的一行。 */
export interface UpdateStepRow {
  /** 原始阶段。 */
  phase: string
  /** 已完成、进行中或待执行。 */
  state: 'done' | 'active' | 'pending'
  /** 进入该阶段的时间（ISO）；旧操作或待执行为空。 */
  at: string | null
  /** 只取真实数据的行内说明，没有时为空字符串。 */
  detail: string
}

/** 一次操作推导出的步骤表。 */
export interface UpdateStepTable {
  rows: UpdateStepRow[]
  /** 已完成行数；只在正向流程有意义。 */
  done: number
  /** 正向流程的总行数；恢复与失败流程为 0，表示不显示「n / m」。 */
  total: number
  /** 当前结局阶段；仍在进行时为空。 */
  outcome: string | null
}

/**
 * 数据库显示名。
 * @param name 接口中的库标识。
 * @return 平台数据库或网关数据库。
 */
export function databaseLabel(name: string): string { return name === 'bench' ? '平台数据库' : '网关数据库'; }

/**
 * 迁移状态文案，未知状态保持原值。
 * @param state 接口中的迁移状态。
 * @return 中文状态。
 */
export function migrationStateLabel(state: string): string {
  return state === 'completed' ? '迁移完成' : state === 'running' ? '正在迁移' : state;
}

/**
 * 数据库快照摘要。
 * @param snapshot 操作中的快照字段。
 * @return 「数据库快照已校验 · 1.0 MiB」或「数据库快照状态：x · …」。
 */
export function snapshotLabel(snapshot: NonNullable<SystemUpdateOperation['database_snapshot']>): string {
  return `数据库快照${snapshot.state === 'verified' ? '已校验' : '状态：' + snapshot.state} · ${(snapshot.bytes / 1024 / 1024).toFixed(1)} MiB`;
}

/**
 * 安装的规范阶段顺序。
 * @param snapshot 部署具备迁移能力，切换前保存快照。
 * @param migrate 目标版本带数据库迁移。
 * @return 阶段列表。
 */
export function canonicalPhases(snapshot: boolean, migrate: boolean): string[] {
  return ['preparing', 'draining', ...(snapshot ? ['snapshotting'] : []), ...(snapshot && migrate ? ['migrating'] : []),
    'switching', 'verifying', 'committing', 'cleaning'];
}

/** 只用操作里的真实数据生成行内说明。 */
function detailOf(phase: string, state: UpdateStepRow['state'], operation: SystemUpdateOperation): string {
  if (phase === 'draining' && state === 'active') {
    const count = operation.blockers?.length ?? 0;
    return count ? `仍有 ${count} 项在途工作，新工作已暂缓` : '等待在途工作自然结束';
  }
  if (phase === 'snapshotting' && operation.database_snapshot) return snapshotLabel(operation.database_snapshot);
  if (phase === 'migrating' && operation.database_migrations) {
    return Object.entries(operation.database_migrations).map(([name, item]) => `${databaseLabel(name)} ${migrationStateLabel(item.state)}`).join(' · ');
  }
  return '';
}

/**
 * 由公开操作推导步骤表：实际记录按顺序成行，维护中补上尚未进入的规范阶段。
 * @param operation 公开操作。
 * @param options snapshot 部署具备快照步骤；migrate 目标版本带迁移；busy 维护仍在进行。
 * @return 行、计数与结局。
 */
export function updateSteps(operation: SystemUpdateOperation, options: { snapshot: boolean; migrate: boolean; busy: boolean }): UpdateStepTable {
  const recorded = (operation.steps ?? []).filter(step => !UPDATE_OUTCOMES.has(step.phase));
  const order = canonicalPhases(options.snapshot, options.migrate || recorded.some(step => step.phase === 'migrating'));
  const outcome = UPDATE_OUTCOMES.has(operation.phase) ? operation.phase : null;
  // 带快照的部署会先以 switching 越过取消边界、再保存快照；这一次只是「等待在途」的结束，不单独成行。
  // 判定：其后还有快照记录，或它是尚未进入快照的最新一条。此时进行中的仍按「等待在途完成」显示。
  const snapshotted = recorded.some(step => step.phase === 'snapshotting');
  const boundary = (step: { phase: string }, index: number) => options.snapshot && step.phase === 'switching'
    && (recorded.slice(index + 1).some(next => next.phase === 'snapshotting') || (!snapshotted && outcome === null && index === recorded.length - 1));
  const steps = recorded.filter((step, index) => !boundary(step, index));
  const current = options.snapshot && operation.phase === 'switching' && recorded.length && !snapshotted ? 'draining' : operation.phase;
  let rows: UpdateStepRow[];
  if (steps.length) {
    // 恢复路径会反复进入同一阶段，只保留最后一次及其时间，保持列表按实际先后排列。
    const sequence: Array<{ phase: string; at: string }> = [];
    for (const step of steps) {
      const index = sequence.findIndex(item => item.phase === step.phase);
      if (index >= 0) sequence.splice(index, 1);
      sequence.push(step);
    }
    rows = sequence.map(step => ({ phase: step.phase, state: 'done', at: step.at, detail: '' }));
  } else if (order.includes(current)) {
    rows = order.slice(0, order.indexOf(current) + 1).map(phase => ({ phase, state: 'done', at: null, detail: '' }));
  } else if (current === 'succeeded') {
    rows = order.map(phase => ({ phase, state: 'done', at: null, detail: '' }));
  } else {
    rows = outcome ? [] : [{ phase: current, state: 'done', at: null, detail: '' }];
  }
  const last = rows[rows.length - 1];
  if (options.busy && outcome === null && last) last.state = 'active';
  if (options.busy && outcome === null && order.includes(current)) {
    const seen = new Set(rows.map(row => row.phase));
    rows.push(...order.slice(order.indexOf(current) + 1).filter(phase => !seen.has(phase))
      .map(phase => ({ phase, state: 'pending' as const, at: null, detail: '' })));
  }
  for (const row of rows) row.detail = detailOf(row.phase, row.state, operation);
  const forward = order.includes(current) || current === 'succeeded';
  return { rows, done: rows.filter(row => row.state === 'done').length, total: forward ? rows.length : 0, outcome };
}
