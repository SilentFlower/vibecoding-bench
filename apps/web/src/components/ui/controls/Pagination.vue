<script setup lang="ts">
import { computed } from 'vue';
import { ChevronLeft, ChevronRight } from '../icon';
import { Button } from '../button';
import PageSizeSelect from './PageSizeSelect.vue';

/** 受控分页；父页面负责查询、取消旧请求及切换条数后回到第一页。 */
const props = withDefaults(defineProps<{
  page: number;
  pageSize: number;
  total: number;
  pageSizes?: readonly number[];
  disabled?: boolean;
  label?: string;
  unit?: string;
  mode?: 'pages' | 'cursor';
  hasPrevious?: boolean;
  hasNext?: boolean;
  canLatest?: boolean;
}>(), { pageSizes: () => [10, 20, 50, 100], disabled: false, label: '列表分页', unit: '条', mode: 'pages' });
const emit = defineEmits<{ 'update:page': [value: number]; 'update:pageSize': [value: number]; latest: [] }>();
const pages = computed(() => Math.max(1, Math.ceil(props.total / props.pageSize)));
const current = computed(() => props.mode==='cursor'?Math.max(1,props.page):Math.min(pages.value, Math.max(1, props.page)));
const previousDisabled = computed(() => props.disabled || (props.mode==='cursor'?!props.hasPrevious:current.value<=1));
const nextDisabled = computed(() => props.disabled || (props.mode==='cursor'?!props.hasNext:current.value>=pages.value));
const visible = computed(() => {
  if (props.mode==='cursor') return [current.value];
  const last = pages.value;
  if (last <= 7) return Array.from({ length: last }, (_, index) => index + 1);
  const start = Math.max(2, Math.min(current.value - 1, last - 3));
  const result: (number | string)[] = [1];
  if (start > 2) result.push('before');
  for (let page = start; page <= Math.min(last - 1, start + 2); page++) result.push(page);
  if (start + 2 < last - 1) result.push('after');
  result.push(last);
  return result;
});
/** 发出单次有效翻页意图，当前页与越界点击保持原状态。@param value 目标页码。@return 无。 */
function changePage(value: number): void {
  if(props.mode==='cursor'){if(value===props.page-1&&!previousDisabled.value||value===props.page+1&&!nextDisabled.value)emit('update:page',value);return;}
  if (!props.disabled && value >= 1 && value <= pages.value && value !== props.page) emit('update:page', value);
}
</script>

<template>
  <div class="fui-pagination" :aria-busy="disabled">
    <div class="fui-pagination-summary"><span>{{ mode==='cursor'?'最新记录在前':`共 ${total} ${unit}` }}</span><PageSizeSelect :model-value="pageSize" :options="pageSizes" :disabled="disabled" @update:model-value="emit('update:pageSize', $event)" /></div>
    <nav class="fui-pagination-controls" :aria-label="label">
      <Button v-if="mode==='cursor'" type="button" variant="outline" size="sm" :disabled="disabled||!canLatest" @click="emit('latest')">最新一页</Button>
      <Button type="button" variant="outline" size="sm" aria-label="上一页" :disabled="previousDisabled" @click="changePage(current - 1)"><ChevronLeft :size="13" /><span class="fui-pagination-direction">上一页</span></Button>
      <template v-for="value in visible" :key="value">
        <Button v-if="typeof value === 'number'" type="button" variant="outline" size="sm" class="fui-pagination-number" :aria-current="value === current ? 'page' : undefined" :aria-label="`第 ${value} 页`" :disabled="disabled" @click="changePage(value)">{{ value }}</Button>
        <span v-else class="fui-pagination-gap" aria-hidden="true">…</span>
      </template>
      <Button type="button" variant="outline" size="sm" aria-label="下一页" :disabled="nextDisabled" @click="changePage(current + 1)"><span class="fui-pagination-direction">下一页</span><ChevronRight :size="13" /></Button>
    </nav>
  </div>
</template>

