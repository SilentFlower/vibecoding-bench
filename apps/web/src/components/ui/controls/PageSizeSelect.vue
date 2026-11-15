<script setup lang="ts">
import { computed, ref } from 'vue';
import ChoiceSelect from './ChoiceSelect.vue';
import '../../../../../legacy-web/pagination.css';

/** 每页条数选择，父列表负责重置页码与取消旧请求。 */
const props = withDefaults(defineProps<{ modelValue: number; options?: readonly number[]; disabled?: boolean; label?: string }>(), { options: () => [10,20,50,100], label: '每页条数' });
const emit = defineEmits<{ 'update:modelValue': [value: number] }>();
const host = ref<HTMLElement>();
const choices = computed(() => props.options.map(value => ({value:String(value),label:`${value} 条 / 页`})));
const portalTarget = computed(() => host.value?.closest<HTMLElement>('[role=dialog],dialog') ?? host.value?.ownerDocument.body);
/** 接收有界页大小，非法浮层值保持原选择。@param value 组件字符串。@return 无。 */
function update(value: string): void {
  const size = Number(value);
  if (props.options.includes(size)) emit('update:modelValue', size);
}
</script>

<template>
  <div ref="host" class="pagination-size"><ChoiceSelect :model-value="String(modelValue)" :options="choices" :label="label" :disabled="disabled" :portal-target="portalTarget" content-class="pagination-size-menu" @update:model-value="update" /></div>
</template>
