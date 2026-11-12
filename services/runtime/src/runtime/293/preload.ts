import type { NativeBindings } from './native';
import { PROFILE_293 } from './source-profile';
import { reportStartupFailure, startWorker } from './worker';

try {
  const modules = await Promise.all(Object.entries(PROFILE_293.modules).map(async ([role, path]) => [role, await import(path)]));
  await startWorker(Object.fromEntries(modules) as NativeBindings);
  // 预加载结束必须退出，避免原 CLI 继续解析 --version 并污染协议通道。
  process.exit(0);
} catch (error) {
  await reportStartupFailure(error);
  process.exit(111);
}
