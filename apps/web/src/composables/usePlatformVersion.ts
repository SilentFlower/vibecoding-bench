import { ref } from 'vue';
import { api } from '../api';
import { parsePlatformVersion } from '../lib/platformVersion';

/**
 * 为视图独立读取当前控制端版本，刷新和卸载时取消原读取。
 * @return 版本引用及受调用方生命周期约束的刷新函数。
 */
export function usePlatformVersion() {
  const version = ref<string | null>(null);
  let pending: AbortController | undefined;

  /** 读取运行时版本，旧请求回执只属于原请求。@param signal 视图生命周期信号。@return 本次读取完成。 */
  async function refresh(signal: AbortSignal): Promise<void> {
    pending?.abort();
    if (signal.aborted) return;
    const current = new AbortController();
    pending = current;
    const abort = () => current.abort();
    signal.addEventListener('abort', abort, { once: true });
    try {
      const value = await api.systemPlatformVersion(current.signal);
      if (!current.signal.aborted && pending === current) version.value = parsePlatformVersion(value?.version);
    } catch {
      // 旧服务或读取失败时使用已验签目录回退；迟到及卸载回执不改变当前视图。
      if (!current.signal.aborted && pending === current) version.value = null;
    } finally {
      signal.removeEventListener('abort', abort);
      if (pending === current) pending = undefined;
    }
  }

  return { version, refresh };
}
