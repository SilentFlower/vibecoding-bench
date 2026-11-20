<script setup lang="ts">
import { computed } from 'vue';
import type { DiagnosticRequest } from '../api';
import { Copy } from './ui/icon';

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
    <code :title="displayedId">{{ displayedId }}</code>
    <small v-if="derived" class="request-session-source">网关派生</small>
    <button type="button" :aria-label="`复制${derived ? '派生' : '原始'} Session ID ${displayedId}`" @click="emit('copy', displayedId, $event)">
      <Copy :size="13" />
    </button>
  </div>
  <span v-else-if="full">未提供</span>
  <small v-else>未提供</small>
</template>
