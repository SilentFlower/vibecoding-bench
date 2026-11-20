<script setup lang="ts">
import { computed } from 'vue';
import { Badge } from '@/components/ui/badge';

/** 显示实际账号平台，历史请求缺少平台时保留未知状态；外观取 Badge 的平台色（设计稿 .tg-cc / .tg-agy）。 */
const props = defineProps<{ platform?: string | null }>();
const label = computed(() => props.platform === 'antigravity' ? '反重力' : props.platform === 'claude_code' ? 'Claude Code' : props.platform || '平台未记录');
const variant = computed(() => props.platform === 'antigravity' ? 'agy' : props.platform === 'claude_code' ? 'cc' : 'secondary');
</script>

<template>
  <Badge :variant="variant" class="platform-badge" :class="platform" data-platform-badge>{{ label }}</Badge>
</template>
