<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { PopoverRoot, PopoverTrigger, PopoverPortal, PopoverContent } from 'reka-ui';
import { Activity, Check, AlertCircle, RefreshCw } from '../icon';
import { Button, type ButtonVariants } from '../button';
/** 与所属业务共享状态，组件只发出显式操作。 */
const props = withDefaults(defineProps<{ status?: 'idle' | 'loading' | 'success' | 'error'; message?: string; label?: string; identity?: string; buttonVariant?: ButtonVariants['variant'] }>(), { status: 'idle', label: '测试' });
const emit = defineEmits<{ action: [] }>();
const open = ref(false);
const portalTarget = ref<HTMLElement>();
const resultOpen = computed({ get: () => open.value && ['success', 'error'].includes(props.status), set: value => { open.value = value && ['success', 'error'].includes(props.status); } });
watch(() => props.status, () => { open.value = false; });
/** 初始点击执行，已有结果时查看详情。@param event 点击事件。@return 无。 */
function activate(event: Event): void {
  if (props.status === 'idle') {
    event.preventDefault();
    emit('action');
    return;
  }
  // 结果和重试按钮留在当前弹窗的焦点范围内，卡片上的结果仍挂载到页面。
  const trigger = event.currentTarget;
  portalTarget.value = trigger instanceof HTMLElement ? trigger.closest<HTMLElement>('[data-slot="dialog-content"]') ?? undefined : undefined;
}
/** 从明确按钮发起新一次操作。@return 无。 */
function retry(): void { open.value = false; emit('action'); }
</script>
<template>
  <PopoverRoot v-model:open="resultOpen">
    <PopoverTrigger :as="buttonVariant ? Button : 'button'" type="button" :variant="buttonVariant ? (status === 'success' || status === 'error' ? 'outline' : buttonVariant) : undefined" class="fui-operation-trigger" :data-status="status" :disabled="status === 'loading'" :aria-label="status === 'idle' ? label : `${label}结果：${status === 'success' ? '连接正常' : status === 'error' ? '测试失败' : '测试中'}`" :aria-busy="status === 'loading'" @click="activate">
      <component :is="status === 'loading' ? RefreshCw : status === 'success' ? Check : status === 'error' ? AlertCircle : Activity" :size="14" :class="{ 'fui-spinning': status === 'loading' }" /><span>{{ status === 'loading' ? '测试中' : status === 'success' ? '正常' : status === 'error' ? '失败' : label }}</span>
    </PopoverTrigger>
    <PopoverPortal :to="portalTarget"><PopoverContent class="fui-operation-result" side="top" align="center" :side-offset="8" :collision-padding="16" @escape-key-down="event => { event.preventDefault(); event.stopPropagation(); open = false; }">
      <header><strong>{{ status === 'success' ? '连接正常' : '测试失败' }}</strong><small>{{ identity }}</small></header><p>{{ message || (status === 'success' ? '账号连接测试已完成。' : '请求未完成，请重试。') }}</p><Button variant="outline" size="sm" @click="retry"><RefreshCw :size="14" />重新测试</Button>
    </PopoverContent></PopoverPortal>
  </PopoverRoot>
</template>

<style scoped>
.fui-operation-trigger[data-slot=button][data-status=success] > * { color: #258269; }
.fui-operation-trigger[data-slot=button][data-status=error] > * { color: var(--destructive); }
</style>
