<script setup lang="ts">
import { useId } from 'vue';
import { CheckboxIndicator, CheckboxRoot } from 'reka-ui';
import { Check, Minus } from '../icon';

/** 复选：默认插槽为可点击文字；indeterminate 表示部分选中，再次点击变为选中。 */
const props = defineProps<{ modelValue: boolean | 'indeterminate'; disabled?: boolean; id?: string }>();
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>();
const generatedId = useId();
</script>

<template>
  <label class="fui-checkbox" data-slot="checkbox" :for="props.id ?? generatedId">
    <CheckboxRoot :id="props.id ?? generatedId" class="fui-checkbox-box" :model-value="modelValue" :disabled="disabled" @update:model-value="value => emit('update:modelValue', value === true)">
      <CheckboxIndicator as-child>
        <Minus v-if="modelValue === 'indeterminate'" :size="12" />
        <Check v-else :size="12" />
      </CheckboxIndicator>
    </CheckboxRoot>
    <span v-if="$slots.default"><slot /></span>
  </label>
</template>
