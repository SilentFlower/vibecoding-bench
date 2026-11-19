<script setup lang="ts">
import { computed } from 'vue';

/** 显示实际账号平台，历史请求缺少平台时保留未知状态。 */
const props = defineProps<{ platform?: string | null }>();
const label = computed(() => props.platform === 'antigravity' ? '反重力' : props.platform === 'claude_code' ? 'Claude Code' : props.platform || '平台未记录');
</script>

<template>
  <span class="platform-badge" :class="platform" data-platform-badge>{{ label }}</span>
</template>

<style scoped>
.platform-badge{display:inline-flex;align-items:center;flex-shrink:0;gap:5px;white-space:nowrap;border:1px solid var(--ui-border,#e2e6ed);border-radius:5px;padding:2px 6px;font-size:var(--ui-font-small,12px);font-weight:500;line-height:1.35;color:var(--ui-muted,#7d879a);background:var(--ui-field-surface,#fbfcfe);}
.platform-badge.claude_code{color:#9b6047;border-color:#eadbd1;background:#fbf5f0;}
.platform-badge.antigravity{color:#4f6f9c;border-color:#d6e2f0;background:#f0f5fc;}
</style>
