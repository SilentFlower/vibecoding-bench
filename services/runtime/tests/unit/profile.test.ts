import { expect, test } from 'bun:test';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { verifyBinary } from '../../src/runtime/profile';
import { createEngine } from '../../src/control/engine';
import { buildRuntime } from '../../scripts/build-runtime';

test('错误版本二进制明确拒绝，不能改个版本字符串就继续或回退演示', async () => {
  const root = await mkdtemp(join(tmpdir(), 'ccrb-profile-test-'));
  try {
    const binaryPath = join(root, 'claude');
    await writeFile(binaryPath, '2.1.293 (Claude Code)');
    await expect(verifyBinary(binaryPath)).rejects.toThrow('校验不匹配');
    await expect(createEngine({ mode: 'native', binaryPath, home: root, configDir: root, preloadPath: '/unavailable', cwd: root, timeoutMs: 1000 })).rejects.toThrow('校验不匹配');
    await writeFile(binaryPath + '.manifest.json', JSON.stringify({ source: '2.1.293', approved: true, bytes: 1 }));
    await expect(verifyBinary(binaryPath)).rejects.toThrow('校验不匹配');
    const output = join(root, 'compact');
    await expect(buildRuntime(['--source', binaryPath, '--out', output])).rejects.toThrow('源程序');
    expect(await Bun.file(output).exists()).toBe(false);
  } finally { await rm(root, { recursive: true, force: true }); }
});
