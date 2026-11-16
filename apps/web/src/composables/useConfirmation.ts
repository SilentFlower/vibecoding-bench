import { shallowRef } from 'vue';

/** 明确操作的说明与按钮文案。 */
export interface ConfirmationOptions { title: string; message: string; confirmLabel?: string; danger?: boolean }
interface PendingConfirmation extends ConfirmationOptions { id: number; finish: (accepted: boolean) => void }
const current = shallowRef<PendingConfirmation | null>(null);
let sequence = 0;

/** 关闭当前确认，仅明确执行按钮传true。@param accepted 用户选择。@return 无。 */
function settle(accepted: boolean): void { current.value?.finish(accepted); }
/** 请求确认，离页取消请求也按取消收口。@param options 操作说明。@param signal 所属工作区生命周期。@return 用户是否明确接受。 */
function ask(options: ConfirmationOptions, signal?: AbortSignal): Promise<boolean> {
  settle(false);
  if (signal?.aborted) return Promise.resolve(false);
  return new Promise(resolve => {
    const id = ++sequence;
    const cancel = () => finish(false);
    const finish = (accepted: boolean) => {
      signal?.removeEventListener('abort', cancel);
      if (current.value?.id === id) current.value = null;
      resolve(accepted);
    };
    current.value = { ...options, id, finish };
    signal?.addEventListener('abort', cancel, { once: true });
  });
}
/** 共享确认宿主与调用接口。@return 确认状态、发起和关闭。 */
export function useConfirmation() { return { current, ask, settle }; }
