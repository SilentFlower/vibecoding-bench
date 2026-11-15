import { onMounted, onUnmounted } from 'vue';

/** 在实际滚动期间显示滚动条，离开应用时清理监听器与计时器。@return 无。 */
export function useActiveScrollbars(): void {
  const timers = new Map<HTMLElement, ReturnType<typeof setTimeout>>();
  /** 标记当前滚动容器，保持轨道宽度稳定。@param event 原生滚动事件。@return 无。 */
  function show(event: Event): void {
    const element = event.target === document ? document.documentElement : event.target;
    if (!(element instanceof HTMLElement)) return;
    clearTimeout(timers.get(element));
    element.dataset.activeScroll = '';
    timers.set(element, setTimeout(() => {
      delete element.dataset.activeScroll;
      timers.delete(element);
    }, 800));
  }
  onMounted(() => document.addEventListener('scroll', show, true));
  onUnmounted(() => {
    document.removeEventListener('scroll', show, true);
    for (const [element, timer] of timers) {
      clearTimeout(timer);
      delete element.dataset.activeScroll;
    }
    timers.clear();
  });
}
