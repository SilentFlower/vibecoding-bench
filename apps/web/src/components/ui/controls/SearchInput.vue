<script setup lang="ts">
import { ref, useId } from 'vue';
import { Search, X } from '@/components/ui/icon';
import './controls.css';

/** 搜索输入仅管理文本，查询时机交由调用方决定。 */
interface Props {
  modelValue: string;
  label: string;
  placeholder?: string;
  disabled?: boolean;
}
defineOptions({ inheritAttrs: false });
defineProps<Props>();
const emit = defineEmits<{ 'update:modelValue': [value: string]; search: [value: string] }>();
const id = useId();
const input = ref<HTMLInputElement>();

/** 透传当前文本，保留业务方的空字符串及筛选语义。@param event 输入事件。@return 无。 */
function update(event: Event): void {
  emit('update:modelValue', (event.target as HTMLInputElement).value);
}

/** 清空后保持输入焦点，便于继续输入新条件。@return 无。 */
function clear(): void {
  emit('update:modelValue', '');
  input.value?.focus();
}

/** 输入法确认阶段不触发业务搜索。@param event 键盘事件。@return 无。 */
function search(event: KeyboardEvent, value: string): void {
  if (event.key !== 'Enter' || event.isComposing) return;
  event.preventDefault();
  emit('search', value);
}
</script>

<template>
  <div class="fui-search" :data-disabled="disabled || undefined">
    <Search :size="15" aria-hidden="true" />
    <input ref="input" v-bind="$attrs" :id="`search-${id}`" type="search" :aria-label="label" :placeholder="placeholder" :value="modelValue" :disabled="disabled" @input="update" @keydown="search($event, modelValue)">
    <button v-if="modelValue" type="button" :aria-label="`清空${label}`" :disabled="disabled" @click="clear"><X :size="13" /></button>
  </div>
</template>
