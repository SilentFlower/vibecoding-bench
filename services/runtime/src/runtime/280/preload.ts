import { PROFILE_280 } from './source-profile';
import { bindNative280 } from './native';
import { reportStartupFailure, startWorker } from '../293/worker';

try {
  const modules = await Promise.all(Object.entries(PROFILE_280.modules).map(async ([role, path]) => [role, await import(path)]));
  await startWorker(bindNative280(Object.fromEntries(modules)));
  process.exit(0);
} catch (error) {
  await reportStartupFailure(error);
  process.exit(111);
}
