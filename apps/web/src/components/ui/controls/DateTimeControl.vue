<script setup lang="ts">
import { computed, ref, watch, useId } from 'vue';
import { CalendarDate, type DateValue } from '@internationalized/date';
import { Calendar, ChevronLeft, ChevronRight } from '../icon';
import { PopoverRoot, PopoverTrigger, PopoverPortal, PopoverContent, CalendarRoot, CalendarHeader, CalendarHeading, CalendarPrev, CalendarNext, CalendarGrid, CalendarGridHead, CalendarHeadCell, CalendarGridBody, CalendarGridRow, CalendarCell, CalendarCellTrigger } from 'reka-ui';
import NumberInput from './NumberInput.vue';

/** 统一日期时间选择，输入输出使用ISO瞬时，界面按浏览器本地时间展示。 */
const props = defineProps<{ modelValue: string | null; label: string; disabled?: boolean; portalTarget?: HTMLElement | string }>();
const emit = defineEmits<{ 'update:modelValue': [value: string | null] }>();
const id = useId();
const open = ref(false);
const timeError = ref('');
const day = ref<DateValue>();
const hours = ref<number | string>(0);
const minutes = ref<number | string>(0);
const display = computed(() => props.modelValue ? new Date(props.modelValue).toLocaleString('zh-CN', { year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit', hour12:false }) : '选择日期与时间');
const valid = computed(() => day.value && hours.value !== '' && minutes.value !== '' && Number.isInteger(Number(hours.value)) && Number.isInteger(Number(minutes.value)) && Number(hours.value) >= 0 && Number(hours.value) <= 23 && Number(minutes.value) >= 0 && Number(minutes.value) <= 59);
watch(open, value => {
  if (!value) return;
  timeError.value='';
  const date = props.modelValue ? new Date(props.modelValue) : new Date();
  day.value = new CalendarDate(date.getFullYear(), date.getMonth() + 1, date.getDate());
  hours.value = date.getHours(); minutes.value = date.getMinutes();
});
/** 提交完整日期草稿。@return 无。 */
function apply(): void {
  if (!valid.value || !day.value) return;
  const value = new Date(day.value.year, day.value.month - 1, day.value.day, Number(hours.value), Number(minutes.value));
  // 夏令时跳时会被Date自动移到下一小时；保留草稿并要求用户明确选择有效时间。
  if(value.getFullYear()!==day.value.year || value.getMonth()!==day.value.month-1 || value.getDate()!==day.value.day || value.getHours()!==Number(hours.value) || value.getMinutes()!==Number(minutes.value)){timeError.value='当前时区不存在这个时间，请选择其他时刻';return;}
  emit('update:modelValue', value.toISOString()); open.value = false;
}
/** 选择本地今天，保留正在编辑的时分。@return 无。 */
function selectToday():void {const value=new Date();day.value=new CalendarDate(value.getFullYear(),value.getMonth()+1,value.getDate());}
watch([day,hours,minutes],()=>{timeError.value='';});
/** Esc只关闭当前日期面板。@param event 键盘事件。@return 无。 */
function escape(event: KeyboardEvent): void { event.preventDefault(); event.stopPropagation(); open.value = false; }
</script>

<template>
  <div class="fui-field">
    <label :for="id" class="fui-label">{{ label }}</label>
    <PopoverRoot v-model:open="open">
      <PopoverTrigger :id="id" class="fui-date-trigger" :aria-label="label" :disabled="disabled"><Calendar :size="16" /><span>{{ display }}</span></PopoverTrigger>
      <PopoverPortal :to="portalTarget"><PopoverContent class="fui-calendar" align="start" :side-offset="6" :collision-padding="12" @escape-key-down="escape">
        <CalendarRoot v-slot="{ grid, weekDays }" v-model="day" locale="zh-CN" :week-starts-on="1" :fixed-weeks="true" :prevent-deselect="true" :calendar-label="label">
          <CalendarHeader class="fui-calendar-header"><CalendarPrev aria-label="上个月"><ChevronLeft :size="16" /></CalendarPrev><CalendarHeading /><CalendarNext aria-label="下个月"><ChevronRight :size="16" /></CalendarNext></CalendarHeader>
          <CalendarGrid v-for="month in grid" :key="month.value.toString()"><CalendarGridHead><CalendarGridRow><CalendarHeadCell v-for="weekday in weekDays" :key="weekday">{{ weekday }}</CalendarHeadCell></CalendarGridRow></CalendarGridHead>
            <CalendarGridBody><CalendarGridRow v-for="(week, index) in month.rows" :key="index"><CalendarCell v-for="date in week" :key="date.toString()" :date="date"><CalendarCellTrigger as="button" type="button" :day="date" :month="month.value" /></CalendarCell></CalendarGridRow></CalendarGridBody>
          </CalendarGrid>
        </CalendarRoot>
        <div class="fui-time-inputs"><NumberInput v-model="hours" label="小时" :min="0" :max="23" /><span>:</span><NumberInput v-model="minutes" label="分钟" :min="0" :max="59" /></div>
        <p v-if="timeError" role="alert" class="fui-date-error">{{ timeError }}</p>
        <div class="fui-calendar-footer"><button type="button" @click="emit('update:modelValue', null); open = false">清除</button><button type="button" @click="selectToday">今天</button><small>本地时间</small><button type="button" :disabled="!valid" @click="apply">确定</button></div>
      </PopoverContent></PopoverPortal>
    </PopoverRoot>
  </div>
</template>
