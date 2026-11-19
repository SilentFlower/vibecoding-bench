<script setup lang="ts">
import { computed } from 'vue';
import { Box } from '../ui/icon';

/** 在账号、环境和历史请求中显示同一节点身份，观察说明由各自数据源提供。 */
const props = withDefaults(defineProps<{
  node?: { node_key: string; node_name?: string; kind?: string } | null;
  status?: string;
  attention?: boolean;
  compact?: boolean;
  emptyLabel?: string;
}>(), { emptyLabel: '节点未观测' });
const name = computed(() => props.node?.node_name || (props.node?.node_key === 'local' ? '默认本机' : '执行节点'));
</script>

<template>
  <div class="execution-node" :class="{ 'execution-node-compact': compact, 'execution-node-attention': attention }" data-execution-node>
    <Box :size="compact ? 12 : 14" class="execution-node-icon" aria-hidden="true" />
    <div class="execution-node-content">
      <div class="execution-node-heading"><span>{{ node ? name : emptyLabel }}</span><small v-if="node?.kind">{{ node.kind === 'local' ? '本机' : 'SSH' }}</small></div>
      <code v-if="node">{{ node.node_key }}</code>
      <span v-if="status" class="execution-node-status">{{ status }}</span>
    </div>
  </div>
</template>

<style scoped>
.execution-node{display:flex;align-items:flex-start;gap:8px;min-width:0;padding:10px 12px;border:1px solid var(--ui-border,#e2e6ed);border-radius:8px;background:var(--ui-field-surface,#fbfcfe);color:var(--ui-text,#46546b);font-size:var(--ui-font-small,12px);line-height:1.5;}
.execution-node-icon{flex-shrink:0;margin-top:3px;opacity:.6;}
.execution-node-content{min-width:0;flex:1;}
.execution-node-heading{display:flex;align-items:baseline;flex-wrap:wrap;gap:4px 8px;}
.execution-node-heading>span{font-weight:500;overflow-wrap:anywhere;}
.execution-node-heading>small{font-size:inherit;color:#65758c;font-weight:400;}
.execution-node code{display:block;max-width:100%;font-family:var(--font-mono,monospace);font-size:inherit;color:#65758c;overflow-wrap:anywhere;word-break:break-all;text-wrap:balance;}
.execution-node-status{display:block;color:#65758c;}
.execution-node-attention .execution-node-status{color:#a5525d;}
.execution-node-compact{padding:0;border:0;background:transparent;gap:5px;}
</style>
