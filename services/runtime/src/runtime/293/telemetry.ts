import type { JsonObject } from '../../shared/contracts';
import { BridgeError } from '../../shared/errors';
import type { TelemetryHandshake, TelemetryPolicy } from '../../shared/runtime-policy';
import type { NativeBindings } from './native';

/** 遥测仅依赖已核对的原生采集、事件分发和网络配置能力。 */
type TelemetryBindings = Pick<NativeBindings, 'analytics' | 'network'> & {
  context: Pick<NativeBindings['context'], 'a4' | 'SLe' | 'MDs' | 'bLe' | 'Jk' | 'gyr' | 'Yus' | 'Nco' | 'w9t' | 'gDn' | 'tt'>;
};

/** 只负责官方第一方遥测的启停和有界收口。 */
export interface NativeTelemetry {
  /** 本地 bootstrap 完成后启用。 @return 官方资格检查及初始化结果。 */
  start(): TelemetryHandshake;
  /** 在进程关闭宽限内等待采集并关闭 logger。 @return 清理完成或预算耗尽。 */
  close(): Promise<void>;
}

/** 为原生事件注册业务上下文筛选，发送、鉴权和指标均保留官方实现。
 * @param bindings 固定版本的原生接口。
 * @param policy 本机启动开关。
 * @param isBusiness 当前异步作用域是否为业务作业，初始化及迟到回调返回 false。
 * @return 待 bootstrap 完成后启动的遥测生命周期。
 */
export function createNativeTelemetry(bindings: TelemetryBindings, policy: TelemetryPolicy, isBusiness: () => boolean): NativeTelemetry {
  process.env.DISABLE_TELEMETRY = '1';
  process.env.CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC = '1';
  process.env.DO_NOT_TRACK = '1';
  process.env.DISABLE_AUTOUPDATER = '1';
  process.env.DISABLE_ERROR_REPORTING = '1';
  process.env.DISABLE_GROWTHBOOK = '1';
  let initialized = false;
  let stopped = false;
  let collecting = false;
  // 仅跟踪尚未完成的官方 metadata 采集，不存储事件或建立另一套上传/重试队列。
  const pending = new Set<Promise<void>>();
  const record = (name: string, metadata: JsonObject = {}): Promise<void> => {
    if (!initialized || stopped || collecting || !isBusiness() || pending.size >= 128) return Promise.resolve();
    // 官方完整 sink 同样阻止同步重入；model/betas/auth 的元数据依赖可能再次记录事件。
    collecting = true;
    try {
      const sample = bindings.context.gyr(name);
      if (sample === 0) return Promise.resolve();
      const task = (async () => {
        // 沿用官方 sink 的顺序：目录就绪后再脱敏，避免在模型别名尚未登记时上传原名。
        if (!bindings.context.Nco()) await bindings.context.w9t();
        const previous = collecting;
        collecting = true;
        let recorded: Promise<void>;
        try {
          try { bindings.context.gDn(bindings.context.tt()); } catch {}
          const filtered = bindings.context.Yus(metadata);
          recorded = bindings.context.Jk(name, sample === null ? filtered : { ...filtered, sample_rate: sample });
        } finally { collecting = previous; }
        await recorded;
      })().catch(() => {});
      pending.add(task);
      void task.then(() => pending.delete(task));
      return task;
    } catch { return Promise.resolve(); }
    finally { collecting = false; }
  };
  // 在 bootstrap 前接住原生队列并丢弃非业务事件；异步作用域防止开启后回放初始化事件。
  // 仅连接第一方采集器，不初始化同时包含第三方通道的完整 CLI analytics sink。
  bindings.analytics.G_o({
    logEvent: (name, metadata) => { void record(name, metadata); },
    logEventAsync: (name, metadata) => { void record(name, metadata); return Promise.resolve(); },
  });
  return {
    start() {
      if (policy === 'off') return { policy, state: 'off' };
      try {
        // 固定 293 使用存在性检查，字符串 0 仍会禁用，开启必须移除关闭键。
        delete process.env.DISABLE_TELEMETRY;
        delete process.env.CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC;
        delete process.env.DO_NOT_TRACK;
        if (!bindings.context.a4()) {
          process.env.DISABLE_TELEMETRY = '1';
          process.env.CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC = '1';
          process.env.DO_NOT_TRACK = '1';
          return { policy, state: 'suppressed' };
        }
        // 官方第一方客户端与模型 FetchSession 使用不同 HTTP 栈，必须配置原生代理/CA 适配。
        bindings.network.Jb();
        bindings.context.SLe();
        initialized = true;
        return { policy, state: 'initialized' };
      } catch { throw new BridgeError('native_configuration', '无法初始化固定运行时的第一方遥测', 503); }
    },
    async close() {
      stopped = true;
      if (!initialized) return;
      let timer: ReturnType<typeof setTimeout> | undefined;
      const closing = (async () => {
        await Promise.allSettled([...pending]);
        // 官方退出路径同样并行开始 exporter 收口与 logger flush，顺序等待可能错过关闭宽限。
        await Promise.allSettled([bindings.context.MDs(), bindings.context.bLe()]);
      })().catch(() => {});
      try { await Promise.race([closing, new Promise<void>(resolve => { timer = setTimeout(resolve, 1000); })]); }
      finally { if (timer) clearTimeout(timer); }
    },
  };
}
