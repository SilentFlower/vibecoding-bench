<script setup lang="ts">
import { RadioGroupItem, RadioGroupRoot } from 'reka-ui';
import type { SegmentedOption } from './types';

/** 单选分段：填充托盘加白色滑块，方向键在选项间循环移动；业务值为字符串。 */
defineProps<{ modelValue: string; options: readonly SegmentedOption[]; label: string; disabled?: boolean }>();
const emit = defineEmits<{ 'update:modelValue': [value: string] }>();

/** 只透传字符串值，忽略底层可能给出的空值。@param value 底层选中值。@return 无。 */
function update(value: unknown): void {
  if (typeof value === 'string') emit('update:modelValue', value);
}
</script>

<template>
  <RadioGroupRoot class="fui-segmented" data-slot="segmented" :model-value="modelValue" :aria-label="label" :disabled="disabled" orientation="horizontal" loop @update:model-value="update">
    <RadioGroupItem v-for="option in options" :key="option.value" class="fui-segmented-item" :value="option.value" :disabled="option.disabled">
      <component :is="option.icon" v-if="option.icon" aria-hidden="true" />
      <span>{{ option.label }}</span>
      <em v-if="option.count != null" class="fui-segmented-count">{{ option.count }}</em>
    </RadioGroupItem>
  </RadioGroupRoot>
</template>
