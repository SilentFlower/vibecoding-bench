<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, shallowRef, watch } from 'vue';
import { useToast } from '../../../composables/useToast';
import { useConfirmation } from '../../../composables/useConfirmation';
import { Check, AlertCircle, X, Clock } from '../icon';
import ConfirmationDialog from './ConfirmationDialog.vue';
const { toasts, dismiss, pause, resume } = useToast();
const { current, settle } = useConfirmation();
const visible = computed(() => toasts.value.slice(-3));
const stack = ref<HTMLElement>();
const portal = shallowRef<HTMLElement | string>('body');
const dialogSelector = '[data-slot="dialog-content"], [role="dialog"][aria-modal="true"], dialog';
let returnFocus: HTMLElement | null = null;
let observer: MutationObserver | undefined;
/** 通知进入当前模态焦点范围，Popover顶层保持视口定位。@return 无。 */
async function syncPortal(): Promise<void> {
  const dialogs = [...document.querySelectorAll<HTMLElement>(dialogSelector)].filter(node => node.getClientRects().length && !node.closest('[inert]') && node.dataset.state !== 'closed' && (!(node instanceof HTMLDialogElement) || node.open));
  const target = dialogs.at(-1) || document.body;
  if (portal.value !== target) portal.value = target;
  await nextTick();
  const element = stack.value;
  if (!element?.isConnected) return;
  if (visible.value.length && !element.matches(':popover-open')) element.showPopover();
  if (!visible.value.length && element.matches(':popover-open')) element.hidePopover();
}
/** 记录进入通知之前的焦点，关闭后返回业务控件。@param event 焦点事件。@return 无。 */
function rememberFocus(event: FocusEvent): void {
  if (event.target instanceof HTMLElement && !stack.value?.contains(event.target)) returnFocus = event.target;
}
/** 只处理当前通知的关闭，保留父弹窗与表单草稿。@param id 消息身份。@return 无。 */
function close(id: number): void {
  const focused = stack.value?.contains(document.activeElement);
  dismiss(id);
  if (focused && returnFocus?.isConnected) returnFocus.focus();
}
/** F8进入通知；通知内Escape只关闭最新消息。@param event 键盘事件。@return 无。 */
function keyboard(event: KeyboardEvent): void {
  if (!visible.value.length) return;
  if (event.key === 'F8') { event.preventDefault(); stack.value?.querySelector<HTMLButtonElement>('.fui-notice-close')?.focus(); }
  if (event.key === 'Escape' && stack.value?.contains(document.activeElement)) { event.preventDefault(); event.stopImmediatePropagation(); close(visible.value[visible.value.length - 1]!.id); }
}
onMounted(() => {
  document.addEventListener('focusin', rememberFocus, true);
  document.addEventListener('keydown', keyboard, true);
  observer = new MutationObserver(records => {
    // 关闭动画会先改变data-state，再移除宿主；两种路径都要迁移仍可见的通知。
    if (visible.value.length && ((portal.value instanceof HTMLElement && !portal.value.isConnected) || records.some(record => record.type === 'attributes'
      ? (record.target as Element).matches(dialogSelector)
      : [...record.addedNodes, ...record.removedNodes].some(node => node instanceof Element && (node.matches(dialogSelector) || node.querySelector(dialogSelector)))))) void syncPortal();
  });
  observer.observe(document.body, { subtree: true, childList: true, attributes: true, attributeFilter: ['open', 'class', 'data-state'] });
});
onUnmounted(() => { observer?.disconnect(); document.removeEventListener('focusin', rememberFocus, true); document.removeEventListener('keydown', keyboard, true); });
watch(() => visible.value.map(item => item.id), (ids, previous = []) => {
  previous.filter(id => !ids.includes(id)).forEach(pause);
  ids.filter(id => !previous.includes(id)).forEach(resume);
  void syncPortal();
}, { immediate: true });
/** 焦点仍在同一通知时继续保持阅读。@param event 焦点离开事件。@param id 通知身份。@return 无。 */
function leave(event: FocusEvent, id: number): void { const element = event.currentTarget as HTMLElement; if (!element.contains(event.relatedTarget as Node | null) && !element.matches(':hover')) resume(id); }
/** 鼠标离开时，键盘仍在阅读的通知继续保持。@param event 指针事件。@param id 通知身份。@return 无。 */
function leavePointer(event: PointerEvent, id: number): void { const element = event.currentTarget as HTMLElement; if (!element.contains(element.ownerDocument.activeElement)) resume(id); }
</script>
<template>
  <Teleport :to="portal">
    <section ref="stack" popover="manual" class="fui-toast-stack" aria-label="操作消息（F8）" aria-live="polite" aria-relevant="additions text">
      <TransitionGroup name="fui-toast">
        <article v-for="item in visible" :key="item.id" class="fui-notice" :data-type="item.type" @pointerenter="pause(item.id)" @pointerleave="leavePointer($event, item.id)" @focusin="pause(item.id)" @focusout="leave($event, item.id)">
          <component :is="item.type === 'success' ? Check : item.type === 'info' ? Clock : AlertCircle" class="fui-notice-icon" :size="20" />
          <div class="fui-notice-copy"><strong>{{ { success: '操作成功', error: '操作未完成', info: '提示', warning: '需要关注' }[item.type] }}</strong><p>{{ item.message }}</p></div>
          <button type="button" class="fui-notice-close" aria-label="关闭消息" @click="close(item.id)"><X :size="16" /></button>
        </article>
      </TransitionGroup>
    </section>
  </Teleport>
  <ConfirmationDialog :open="!!current" :title="current?.title || '确认操作'" :message="current?.message" :confirm-label="current?.confirmLabel" :danger="current?.danger" @confirm="settle(true)" @cancel="settle(false)" />
</template>
