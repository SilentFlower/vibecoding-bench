import { BridgeError, isObject } from '../../src/shared/errors';

/** 仅描述实际经过的本地初始化步骤，不推断历史故障或模型执行状态。 */
export const LOCAL_POOL_STARTUP_STAGES = ['unknown', 'workspace', 'certificate', 'forwarder_build', 'node', 'proxy_environment', 'forwarder_start', 'tls_listen', 'tls_probe', 'forwarder_verify', 'driver_start', 'driver_isolation', 'proxy_start', 'proxy_probe', 'driver_setup', 'runtime_verify'] as const;
/** 可跨私有边界传递的固定原因，不含任意异常原文。 */
export const LOCAL_POOL_STARTUP_CODES = ['UNKNOWN', 'CERTIFICATE_GENERATION_FAILED', 'BUILD_FAILED', 'NODE_NOT_FOUND', 'PROXY_CONFIG_UNSUPPORTED', 'INIT_FRAME_INVALID', 'RAW_HEADERS_MISMATCH', 'ISOLATION_CHECK_FAILED', 'TARGET_REJECTION_FAILED', 'RUNTIME_VERIFY_FAILED', 'CHANNEL_TIMEOUT', 'CHANNEL_CLOSED', 'CHANNEL_TRUNCATED', 'CHANNEL_INVALID', 'ENOENT', 'EACCES', 'EPERM', 'EADDRINUSE', 'ECONNREFUSED', 'ECONNRESET', 'EPIPE', 'CERT_NOT_YET_VALID', 'CERT_HAS_EXPIRED', 'DEPTH_ZERO_SELF_SIGNED_CERT', 'UNABLE_TO_VERIFY_LEAF_SIGNATURE', 'ERR_TLS_CERT_ALTNAME_INVALID'] as const;
/** 允许在初始化阶段更新的受控标记。 */
export type LocalPoolStartupStage = typeof LOCAL_POOL_STARTUP_STAGES[number];
/** 可展示的启动证据；字段缺失或不受支持时明确降为未知。 */
export interface LocalPoolStartupDiagnostics {
  stage: LocalPoolStartupStage;
  failureCode: typeof LOCAL_POOL_STARTUP_CODES[number];
}

/** 重建最小白名单对象，禁止私有帧扩展字段进入说明。
 * @param value 待校验的私有诊断。
 * @return 仅包含阶段和受控原因的对象。
 */
export function decodeLocalPoolStartup(value: unknown): LocalPoolStartupDiagnostics {
  return {
    stage: LOCAL_POOL_STARTUP_STAGES.find(stage => isObject(value) && value.stage === stage) ?? 'unknown',
    failureCode: LOCAL_POOL_STARTUP_CODES.find(code => isObject(value) && value.failureCode === code) ?? 'UNKNOWN',
  };
}

/** 保留启动首错的安全证据，不携带原始 cause 或子进程输出。 */
export class LocalPoolStartupError extends BridgeError {
  readonly startup: LocalPoolStartupDiagnostics;
  /** 构造可供本地 CLI 展示的启动错误。
   * @param stage 宿主已观测的失败阶段。
   * @param error 明确代码或原始异常，仅读取其直接白名单 code。
   */
  constructor(stage: LocalPoolStartupStage, error: unknown) {
    const child = error instanceof LocalPoolStartupError ? error.startup : undefined;
    const startup = decodeLocalPoolStartup({ stage: child?.stage === 'unknown' ? stage : child?.stage ?? stage, failureCode: child?.failureCode ?? (isObject(error) ? error.code : error) });
    super('local_pool_startup', '本地池联调初始化失败；阶段：' + startup.stage + '；原因：' + startup.failureCode + '；未发起池推理', 503);
    this.startup = startup;
  }
}
