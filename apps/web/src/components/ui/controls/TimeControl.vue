<script setup lang="ts">
import { ref } from 'vue';
import { Clock } from 'lucide-vue-next';
import { PopoverRoot, PopoverTrigger, PopoverPortal, PopoverContent } from 'reka-ui';
import NumberInput from './NumberInput.vue';
import { Button } from '../button';
import './controls.css';

/** 当地时分选择，无日期或时区换算；取消保留原值。 */
const props = defineProps<{ modelValue: string; label: string; disabled?: boolean }>();
const emit = defineEmits<{ 'update:modelValue': [value: string] }>();
const open = ref(false), hours = ref<number | string>(0), minutes = ref<number | string>(0);
/** 打开时复制草稿，关闭丢弃未确认内容。@param value 是否打开。@return 无。 */
function toggle(value: boolean): void { if (value) { const parts=props.modelValue.split(':');hours.value=Number(parts[0]||0);minutes.value=Number(parts[1]||0); } open.value=value; }
/** 保存有效HH:mm。@return 无。 */
function apply(): void { const hour=Number(hours.value),minute=Number(minutes.value);if(hours.value===''||minutes.value===''||!Number.isInteger(hour)||hour<0||hour>23||!Number.isInteger(minute)||minute<0||minute>59)return;emit('update:modelValue',`${String(hour).padStart(2,'0')}:${String(minute).padStart(2,'0')}`);open.value=false; }
</script>
<template>
  <div class="fui-field"><span class="fui-label">{{ label }}</span><PopoverRoot :open="open" @update:open="toggle"><PopoverTrigger class="fui-date-trigger" :aria-label="label" :disabled="disabled"><Clock :size="15" />{{ modelValue }}</PopoverTrigger><PopoverPortal><PopoverContent class="fui-calendar fui-clock" align="start" :side-offset="6" :collision-padding="12" @escape-key-down="event=>{event.preventDefault();event.stopPropagation();open=false;}"><div class="fui-time-inputs"><NumberInput v-model="hours" label="小时" :min="0" :max="23" /><span>:</span><NumberInput v-model="minutes" label="分钟" :min="0" :max="59" /></div><div class="fui-clock-actions"><Button type="button" variant="outline" @click="open=false">取消</Button><Button type="button" @click="apply">确认</Button></div></PopoverContent></PopoverPortal></PopoverRoot></div>
</template>
<style scoped>
.fui-clock{width:280px}.fui-clock-actions{display:flex;justify-content:flex-end;gap:8px;padding-top:12px}
</style>
