import { randomUUID } from 'node:crypto';
import { closeSync, openSync, readSync } from 'node:fs';
import { BridgeError } from '../../shared/errors';
import { PROFILE_293 } from './source-profile';

/** 恢复受控快照后的主执行域随机状态。
 * @return 原生 UUID 缓存和主执行域 Math.random 已重新初始化。
 * @remarks 控制器须先在所有线程暂停时重置已核验的 BoringSSL WIPEONFORK 标志。
 */
export async function resetRestoredRandomState(): Promise<void> {
  const profile = PROFILE_293.restore;
  if (Bun.version !== profile.bunVersion || Bun.revision !== profile.bunRevision) throw new BridgeError('native_configuration', '恢复运行时随机状态配方不匹配', 503);
  const { heapStats, setRandomSeed } = await import('bun:jsc');
  const stats = heapStats();
  // 固定构建保留一个只供内置 UI 声明的 NodeVM；业务脚本只在主执行域构造。
  const main = stats.objectTypeCounts.GlobalObject ?? 0;
  const declarations = stats.objectTypeCounts.NodeVMGlobalObject ?? 0;
  if (main !== 1 || declarations > 1 || stats.globalObjectCount !== main + declarations) throw new BridgeError('native_configuration', '恢复运行时存在未登记的执行域', 503);
  // Bun 1.4.3 的 UUID 池为 2048 字节。原生 DRBG 已识别新的 fork 代次后，
  // 耗尽旧池并触发补充，避免缓存中快照前的字节进入后续业务 UUID。
  for (let index = 0; index <= profile.entropyCacheBytes / 16; index++) randomUUID();
  const seed = Buffer.alloc(4);
  const descriptor = openSync('/dev/urandom', 'r');
  try {
    if (readSync(descriptor, seed, 0, seed.length, null) !== seed.length) throw new BridgeError('native_configuration', '恢复运行时随机种子读取失败', 503);
  } finally { closeSync(descriptor); }
  setRandomSeed(seed.readUInt32LE(0));
}
