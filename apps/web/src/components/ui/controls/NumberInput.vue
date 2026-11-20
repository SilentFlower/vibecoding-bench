<script setup lang="ts">
import { computed, ref, useId } from 'vue';

/** 数字输入契约：清空产生空字符串，范围校验由原生输入与业务提交共同负责。插槽 label-extra 放在标签元素之后（如「已修改」），不进入无障碍名称。 */
interface Props {
  modelValue?: number | string;
  label: string;
  id?: string;
  min?: number;
  max?: number;
  step?: number;
  disabled?: boolean;
  readonly?: boolean;
  invalid?: boolean;
}
defineOptions({ inheritAttrs: false });
const props = withDefaults(defineProps<Props>(), { step: 1 });
const emit = defineEmits<{ 'update:modelValue': [value: number | string] }>();
const generatedId = useId();
const inputId = computed(() => props.id ?? `number-${generatedId}`);
const input = ref<HTMLInputElement>();
const value = computed(() => props.modelValue === '' || props.modelValue == null ? NaN : Number(props.modelValue));
const locked = computed(() => props.disabled || props.readonly);

/** 保留空输入语义，避免清空自动变为零。@param event 原生输入事件。@return 无。 */
function update(event: Event): void {
  const target = event.target as HTMLInputElement;
  emit('update:modelValue', target.value === '' ? '' : target.valueAsNumber);
}

/** 复用浏览器的步长和范围规则。@param direction 增减方向。@return 无。 */
function increment(direction: number): void {
  if (!input.value || locked.value) return;
  input.value.stepUp(direction);
  input.value.dispatchEvent(new Event('input', { bubbles: true }));
  input.value.dispatchEvent(new Event('change', { bubbles: true }));
}
</script>

<template>
  <div class="fui-field">
    <div v-if="$slots['label-extra']" class="fui-label-row"><label :for="inputId" class="fui-label">{{ label }}</label><slot name="label-extra" /></div>
    <label v-else :for="inputId" class="fui-label">{{ label }}</label>
    <div class="fui-number" :data-invalid="invalid || undefined" :data-disabled="disabled || undefined">
      <input
        v-bind="$attrs" :id="inputId" ref="input" type="number" inputmode="decimal"
        :value="modelValue" :min="min" :max="max" :step="step" :disabled="disabled"
        :readonly="readonly" :aria-invalid="invalid || undefined" @input="update"
      >
      <div class="fui-stepper">
        <button type="button" :aria-label="`减少${label}`" :disabled="locked || (min != null && value <= min)" @click="increment(-1)">−</button>
        <button type="button" :aria-label="`增加${label}`" :disabled="locked || (max != null && value >= max)" @click="increment(1)">+</button>
      </div>
    </div>
  </div>
</template>
