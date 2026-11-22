<script setup lang="ts">
import { computed } from 'vue';
import type { DiagnosticRequest } from '../api';
import { Copy } from './ui/icon';

/**
 * 请求记录的 Session ID 单元：优先显示客户端原始值，缺省时显示网关派生值并加标记。
 * @prop request 请求根记录中的两个 Session 字段。
 * @prop full 详情概览使用，完整换行展示；列表态单行省略。
 * @emits copy 复制当前展示字段的完整字符串。
 */
const props = defineProps<{
  request: Pick<DiagnosticRequest, 'original_session_id' | 'derived_session_id'>;
  full?: boolean;
}>();
const emit = defineEmits<{ copy: [value: string, event: MouseEvent] }>();

const displayedId = computed(() => props.request.original_session_id || props.request.derived_session_id);
const derived = computed(() => !props.request.original_session_id && !!props.request.derived_session_id);
</script>

<template>
  <div v-if="displayedId" class="request-session" :class="{ 'request-session-full': full }">
    <code :class="{ 'fui-table-mono': !full }" :title="displayedId">{{ displayedId }}</code>
    <small v-if="derived" class="request-session-source">网关派生</small>
    <button type="button" class="request-copy" :aria-label="`复制${derived ? '派生' : '原始'} Session ID ${displayedId}`" @click="emit('copy', displayedId, $event)">
      <Copy :size="12" />
    </button>
  </div>
  <span v-else-if="full">未提供</span>
  <span v-else class="request-missing">未提供</span>
</template>
