import type { RuntimeEvent } from '../../src/shared/contracts';
import type { TelemetryState } from '../../src/shared/runtime-policy';
import { isObject } from '../../src/shared/errors';
import { validateRuntimeEvent } from '../../src/shared/protocol';
import { decodeLocalPoolStartup, type LocalPoolStartupDiagnostics } from './local-pool-startup';

/** 手工驱动的初始化信息，不含池地址与真实凭据。 */
export interface LocalDriverSetup { root: string; socketPath: string; certFile: string; binary: string }
/** 单次引擎异常只公开已脱敏的合同说明。 */
export interface LocalDriverError { code: string; message: string; status: number }
/** 独立驱动的单一读取器协议，事件沿用产品 RuntimeEvent。 */
export type LocalDriverFrame =
  | { type: 'ready'; namespace: string; interfaces: string[]; envNames: string[]; rejectedTargetProbe: boolean; name: string; binarySha256: string }
  | { type: 'event'; event: RuntimeEvent; workerPid: number | null }
  | { type: 'idle'; requestId: string; workerPid: number | null; telemetryState: TelemetryState; workerEnvNames: string[]; syntheticCredential: boolean; error?: LocalDriverError }
  | { type: 'fatal'; message: string; startup?: LocalPoolStartupDiagnostics };

/** 校验私有驱动帧，不能让 HTTP 输入伪造进程事件。
 * @param line 完整 JSONL 行。
 * @return 已验证的驱动消息。
 */
export function decodeLocalDriverFrame(line: string): LocalDriverFrame {
  const value: unknown = JSON.parse(line);
  const strings = (x: unknown): x is string[] => Array.isArray(x) && x.every(item => typeof item === 'string');
  const pid = (x: unknown): boolean => x === null || Number.isSafeInteger(x) && Number(x) > 0;
  if (isObject(value)) {
    if (value.type === 'fatal' && typeof value.message === 'string') return { type: 'fatal', message: '本地隔离驱动失败，未自动重放', ...(value.startup === undefined ? {} : { startup: decodeLocalPoolStartup(value.startup) }) };
    if (value.type === 'ready' && typeof value.namespace === 'string' && strings(value.interfaces) && strings(value.envNames) && value.rejectedTargetProbe === true && typeof value.name === 'string' && typeof value.binarySha256 === 'string' && /^[a-f0-9]{64}$/.test(value.binarySha256)) return value as unknown as LocalDriverFrame;
    if (value.type === 'event' && isObject(value.event) && typeof value.event.request_id === 'string' && pid(value.workerPid)) {
      validateRuntimeEvent(value.event, value.event.request_id);
      return value as unknown as LocalDriverFrame;
    }
    if (value.type === 'idle' && typeof value.requestId === 'string' && pid(value.workerPid) && strings(value.workerEnvNames) && typeof value.syntheticCredential === 'boolean' && ['off','pending','initialized','suppressed','unavailable'].includes(String(value.telemetryState))) {
      if (value.error !== undefined && (!isObject(value.error) || typeof value.error.code !== 'string' || typeof value.error.message !== 'string' || !Number.isInteger(value.error.status) || Number(value.error.status) < 400 || Number(value.error.status) > 599)) throw new Error('本地驱动异常格式错误');
      return value as unknown as LocalDriverFrame;
    }
  }
  throw new Error('本地驱动私有帧格式错误');
}
