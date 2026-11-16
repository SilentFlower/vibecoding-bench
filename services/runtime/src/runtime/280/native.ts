import type { NativeBindings } from '../293/native';
import { NATIVE_ALIASES_280, PROFILE_280 } from './source-profile';

/** 将已核验280模块映射到共享桥接接口，保留原生函数与对象。
 * @param modules 从固定来源加载的原生模块。
 * @return 具备明确来源版本的共享绑定。
 */
export function bindNative280(modules: Record<string, Record<string, unknown>>): NativeBindings {
  const bindings: Record<string, Record<string, unknown>> = {};
  for (const [role, names] of Object.entries(NATIVE_ALIASES_280)) {
    bindings[role] = {};
    for (const [name, original] of Object.entries(names)) {
      if (!Object.hasOwn(modules[role] ?? {}, original)) throw new Error('280原生接口缺失：' + role + '.' + original);
      bindings[role]![name] = modules[role]![original];
    }
  }
  // 280的SDK默认发送器直接使用原生fetch；FetchSession属于293新增接口。
  bindings.api!.Ree = globalThis.fetch.bind(globalThis);
  // 280用户实体没有293新增的turnPosition，保持原版的省略语义。
  bindings.core!.Fyn = () => undefined;
  return { ...bindings, sourceVersion: PROFILE_280.version } as unknown as NativeBindings;
}
