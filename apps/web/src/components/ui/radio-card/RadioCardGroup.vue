<script setup lang="ts">
import { RadioGroupItem, RadioGroupRoot } from 'reka-ui';
import type { RadioCardOption } from './types';

/** 单选卡组：每项带标题与说明，选中项主色描边；name 存在时随表单提交。 */
defineProps<{ modelValue?: string; options: readonly RadioCardOption[]; label: string; name?: string; disabled?: boolean }>();
const emit = defineEmits<{ 'update:modelValue': [value: string] }>();

/** 只透传字符串值。@param value 底层选中值。@return 无。 */
function update(value: unknown): void {
  if (typeof value === 'string') emit('update:modelValue', value);
}
</script>

<template>
  <RadioGroupRoot class="fui-radio-cards" data-slot="radio-cards" :model-value="modelValue" :name="name" :aria-label="label" :disabled="disabled" loop @update:model-value="update">
    <RadioGroupItem v-for="option in options" :key="option.value" class="fui-radio-card" :value="option.value" :disabled="option.disabled">
      <span class="fui-radio-card-dot" aria-hidden="true" />
      <span>
        <span class="fui-radio-card-label">{{ option.label }}</span>
        <span v-if="option.description" class="fui-radio-card-description">{{ option.description }}</span>
      </span>
    </RadioGroupItem>
  </RadioGroupRoot>
</template>
