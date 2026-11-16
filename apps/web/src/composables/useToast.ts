import { ref } from 'vue';

/** 操作反馈的公开语义，不依赖消息文本猜测严重程度。 */
export type FeedbackType = 'success' | 'error' | 'info' | 'warning';
/** 一条可独立关闭的反馈。 */
export interface Toast { id: number; message: string; type: FeedbackType }
interface Timer { remaining: number; started: number; handle?: ReturnType<typeof setTimeout> }
const toasts = ref<Toast[]>([]);
const timers = new Map<number, Timer>();
let nextId = 0;

/** 关闭消息并释放计时器。@param id 消息身份。@return 无。 */
function dismiss(id: number): void {
  clearTimeout(timers.get(id)?.handle);
  timers.delete(id);
  toasts.value = toasts.value.filter(item => item.id !== id);
}
/** 暂停正在阅读的消息。@param id 消息身份。@return 无。 */
function pause(id: number): void {
  const timer = timers.get(id);
  if (!timer?.handle) return;
  clearTimeout(timer.handle);
  timer.remaining = Math.max(1, timer.remaining - (performance.now() - timer.started));
  timer.handle = undefined;
}
/** 只对可见消息计时，隐藏队列不会提前消失。@param id 消息身份。@return 无。 */
function resume(id: number): void {
  const timer = timers.get(id);
  if (!timer || timer.handle || timer.remaining === 0) return;
  timer.started = performance.now();
  timer.handle = setTimeout(() => dismiss(id), timer.remaining);
}
/** 添加结果通知，兼容原调用方式。@param message 文本。@param type 语义。@param duration 显示时长，0为手动关闭。@return 消息身份。 */
function show(message: string, type: FeedbackType = 'error', duration = type === 'error' || type === 'warning' ? 0 : 4000): number {
  const duplicate = toasts.value.find(item => item.type === type && item.message === message);
  if (duplicate) dismiss(duplicate.id);
  // 有界保留最新反馈，避免后台连续错误使通知队列无限增长。
  while (toasts.value.length >= 12) dismiss(toasts.value[0]!.id);
  const id = nextId++;
  timers.set(id, { remaining: Math.max(0, duration), started: 0 });
  toasts.value.push({ id, message, type });
  return id;
}
/** 提供全站同一份通知状态及生命周期操作。@return 通知接口。 */
export function useToast() { return { toasts, show, dismiss, pause, resume }; }
