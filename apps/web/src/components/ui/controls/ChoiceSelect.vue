<script setup lang="ts">
import { computed, ref, useId } from 'vue';
import { Check, ChevronDown } from '../icon';
import { SelectRoot, SelectTrigger, SelectValue, SelectIcon, SelectPortal, SelectContent, SelectViewport, SelectItem, SelectItemText, SelectItemIndicator } from 'reka-ui';
import type { ChoiceOption } from './types';

/** 单选控件的表单与浮层属性；空字符串可作为合法选项值。插槽 label-extra 放在标签元素之后，不进入无障碍名称。 */
interface Props {
  modelValue?: string;
  options: readonly ChoiceOption[];
  label: string;
  name?: string;
  placeholder?: string;
  disabled?: boolean;
  required?: boolean;
  invalid?: boolean;
  portalTarget?: HTMLElement | string;
  contentClass?: string;
}
const props = withDefaults(defineProps<Props>(), { placeholder: '请选择' });
const emit = defineEmits<{ 'update:modelValue': [value: string] }>();
const id = useId();
const open = ref(false);
// 组件内部编码全部选项，避免空业务值与底层菜单的占位值冲突。
const selectedIndex = computed(() => props.options.findIndex(option => option.value === props.modelValue));
const encodedValue = computed(() => selectedIndex.value < 0 ? undefined : `option-${selectedIndex.value}`);
const missing = computed(() => props.modelValue !== undefined && selectedIndex.value < 0);

/** 将组件内部值还原为调用方的原始字符串。@param encoded 菜单内部值。@return 无。 */
function update(encoded: unknown): void {
  if (typeof encoded !== 'string' || !/^option-\d+$/.test(encoded)) return;
  const option = props.options[Number(encoded.slice(7))];
  if (option && !option.disabled) emit('update:modelValue', option.value);
}

/** 关闭当前菜单，阻止同次Esc触发原生父dialog关闭。@param event 键盘事件。@return 无。 */
function closeOnEscape(event: KeyboardEvent): void {
  event.preventDefault();
  event.stopPropagation();
  open.value = false;
}
</script>

<template>
  <div class="fui-field">
    <div v-if="$slots['label-extra']" class="fui-label-row"><label :id="`choice-label-${id}`" :for="`choice-${id}`" class="fui-label">{{ label }}</label><slot name="label-extra" /></div>
    <label v-else :id="`choice-label-${id}`" :for="`choice-${id}`" class="fui-label">{{ label }}</label>
    <input v-if="name" type="hidden" :name="name" :value="modelValue" :disabled="disabled">
    <SelectRoot v-model:open="open" :model-value="encodedValue" :disabled="disabled" :required="required" @update:model-value="update">
      <SelectTrigger :id="`choice-${id}`" class="fui-choice" :aria-labelledby="`choice-label-${id}`" :aria-invalid="invalid || undefined">
        <SelectValue :placeholder="missing ? '当前选项不可用' : placeholder" />
        <SelectIcon><ChevronDown :size="14" /></SelectIcon>
      </SelectTrigger>
      <SelectPortal :to="portalTarget">
        <SelectContent class="fui-choice-menu" :class="contentClass" position="popper" align="start" :side-offset="6" :collision-padding="12" :body-lock="false" @escape-key-down="closeOnEscape">
          <SelectViewport>
            <SelectItem v-for="(option, index) in options" :key="option.value" class="fui-choice-option" :value="`option-${index}`" :disabled="option.disabled" :text-value="option.label">
              <SelectItemText>{{ option.label }}</SelectItemText>
              <SelectItemIndicator><Check :size="14" /></SelectItemIndicator>
            </SelectItem>
            <p v-if="options.length === 0" class="fui-empty">暂无可选项</p>
          </SelectViewport>
        </SelectContent>
      </SelectPortal>
    </SelectRoot>
  </div>
</template>
