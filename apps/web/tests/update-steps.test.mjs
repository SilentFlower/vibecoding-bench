import assert from 'node:assert/strict';
import test from 'node:test';
import { canonicalPhases, updateSteps } from '../src/lib/updateSteps.ts';

const base = { operation_id: 'op', action: 'install', target_release: 'system-ci-2-1', created_at: '2026-11-20T00:00:00Z', updated_at: '2026-11-20T00:00:00Z' };
const at = index => `2026-11-20T00:00:${String(index).padStart(2, '0')}Z`;
const steps = phases => phases.map((phase, index) => ({ phase, at: at(index) }));
const view = table => table.rows.map(row => `${row.phase}:${row.state}${row.at ? '@' + row.at.slice(17, 19) : ''}`);

test('规范顺序按快照与迁移能力增减步骤', () => {
  assert.deepEqual(canonicalPhases(false, true), ['preparing', 'draining', 'switching', 'verifying', 'committing', 'cleaning']);
  assert.deepEqual(canonicalPhases(true, false), ['preparing', 'draining', 'snapshotting', 'switching', 'verifying', 'committing', 'cleaning']);
  assert.deepEqual(canonicalPhases(true, true).slice(2, 5), ['snapshotting', 'migrating', 'switching']);
});

test('维护中：最后一条进行中，其余已完成并带时间，补上待执行', () => {
  const table = updateSteps({ ...base, phase: 'draining', blockers: ['a', 'b'], steps: steps(['preparing', 'draining']) }, { snapshot: true, migrate: true, busy: true });
  assert.deepEqual(view(table), ['preparing:done@00', 'draining:active@01', 'snapshotting:pending', 'migrating:pending',
    'switching:pending', 'verifying:pending', 'committing:pending', 'cleaning:pending']);
  assert.equal(table.rows[1].detail, '仍有 2 项在途工作，新工作已暂缓');
  assert.deepEqual([table.done, table.total, table.outcome], [1, 8, null]);
});

test('越过取消边界的第一次切换不单独成行，进行中仍显示等待在途', () => {
  const boundary = updateSteps({ ...base, phase: 'switching', steps: steps(['preparing', 'draining', 'switching']) }, { snapshot: true, migrate: true, busy: true });
  assert.deepEqual(view(boundary).slice(0, 3), ['preparing:done@00', 'draining:active@01', 'snapshotting:pending']);
  assert.equal(boundary.rows[1].detail, '等待在途工作自然结束');
  const done = updateSteps({ ...base, phase: 'succeeded', database_snapshot: { state: 'verified', bytes: 1048576, completed_at: at(3) },
    database_migrations: { bench: { state: 'completed', target_version: 1 }, gateway: { state: 'running', target_version: 1 } },
    steps: steps(['preparing', 'draining', 'switching', 'snapshotting', 'migrating', 'switching', 'verifying', 'committing', 'cleaning', 'succeeded']) },
  { snapshot: true, migrate: false, busy: false });
  assert.deepEqual(view(done), ['preparing:done@00', 'draining:done@01', 'snapshotting:done@03', 'migrating:done@04', 'switching:done@05',
    'verifying:done@06', 'committing:done@07', 'cleaning:done@08']);
  assert.equal(done.rows[2].detail, '数据库快照已校验 · 1.0 MiB');
  assert.equal(done.rows[3].detail, '平台数据库 迁移完成 · 网关数据库 正在迁移');
  assert.deepEqual([done.done, done.total, done.outcome], [8, 8, 'succeeded']);
});

test('没有快照能力的部署保留唯一一次切换', () => {
  const table = updateSteps({ ...base, phase: 'switching', steps: steps(['preparing', 'draining', 'switching']) }, { snapshot: false, migrate: false, busy: true });
  assert.deepEqual(view(table), ['preparing:done@00', 'draining:done@01', 'switching:active@02', 'verifying:pending', 'committing:pending', 'cleaning:pending']);
});

test('恢复路径按实际先后列出，重复阶段只留最后一次，不显示计数', () => {
  const running = updateSteps({ ...base, phase: 'restoring', steps: steps(['preparing', 'draining', 'switching', 'verifying', 'restoring', 'restoring_data', 'restoring']) },
    { snapshot: false, migrate: false, busy: true });
  assert.deepEqual(view(running), ['preparing:done@00', 'draining:done@01', 'switching:done@02', 'verifying:done@03', 'restoring_data:done@05', 'restoring:active@06']);
  assert.equal(running.total, 0);
  const restored = updateSteps({ ...base, phase: 'restored', error: '合成验收失败', steps: steps(['preparing', 'draining', 'switching', 'verifying', 'restoring', 'restored']) },
    { snapshot: false, migrate: false, busy: false });
  assert.equal(restored.outcome, 'restored');
  assert.equal(restored.rows.at(-1).phase, 'restoring');
  assert.ok(restored.rows.every(row => row.state === 'done'));
});

test('旧操作没有步骤记录时按当前阶段推出', () => {
  const running = updateSteps({ ...base, phase: 'verifying', steps: null }, { snapshot: false, migrate: false, busy: true });
  assert.deepEqual(view(running), ['preparing:done', 'draining:done', 'switching:done', 'verifying:active', 'committing:pending', 'cleaning:pending']);
  const finished = updateSteps({ ...base, phase: 'succeeded' }, { snapshot: true, migrate: false, busy: false });
  assert.equal(finished.rows.length, 7);
  assert.deepEqual([finished.done, finished.total], [7, 7]);
  const failed = updateSteps({ ...base, phase: 'failed', error: '执行在准备阶段中断' }, { snapshot: false, migrate: false, busy: false });
  assert.deepEqual([failed.rows, failed.outcome, failed.total], [[], 'failed', 0]);
  const unknown = updateSteps({ ...base, phase: 'synthetic-new-phase' }, { snapshot: false, migrate: false, busy: true });
  assert.deepEqual(view(unknown), ['synthetic-new-phase:active']);
});

test('截断后的记录照常成表', () => {
  const tail = Array.from({ length: 64 }, (_, index) => index % 2 ? 'restoring' : 'restoring_data');
  const table = updateSteps({ ...base, phase: 'reconcile', steps: [...steps(tail), { phase: 'reconcile', at: at(70) }] }, { snapshot: false, migrate: false, busy: true });
  assert.deepEqual(table.rows.map(row => row.phase), ['restoring_data', 'restoring']);
  assert.equal(table.outcome, 'reconcile');
  assert.ok(table.rows.every(row => row.state === 'done'));
});
