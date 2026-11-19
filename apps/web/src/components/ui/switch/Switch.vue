<script setup lang="ts">
import { SwitchRoot, SwitchThumb } from 'reka-ui';

/** 开关只表达布尔值；没有关联的可见文字时，用 label 提供无障碍名称。 */
defineProps<{ modelValue: boolean; label?: string; disabled?: boolean; id?: string }>();
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>();
</script>

<template>
  <SwitchRoot :id="id" class="fui-switch" data-slot="switch" :model-value="modelValue" :disabled="disabled" :aria-label="label" @update:model-value="value => emit('update:modelValue', value === true)">
    <SwitchThumb class="fui-switch-thumb" />
  </SwitchRoot>
</template>
