<script setup lang="ts">
import { computed } from 'vue';
import { TooltipProvider, TooltipRoot, TooltipTrigger, TooltipPortal, TooltipContent } from 'reka-ui';
import { Server } from '../ui/icon';

/** 在账号、环境和历史请求中显示同一节点身份，观察说明由各自数据源提供。 */
const props = withDefaults(defineProps<{
  node?: { node_key: string; node_name?: string; kind?: string } | null;
  status?: string;
  attention?: boolean;
  compact?: boolean;
  emptyLabel?: string;
}>(), { emptyLabel: '节点未观测' });
const name = computed(() => props.node?.node_name || (props.node?.node_key === 'local' ? '默认本机' : props.node?.node_key));
</script>

<template>
  <TooltipProvider :delay-duration="150">
    <TooltipRoot>
      <TooltipTrigger as-child>
        <router-link :to="{ name: 'nodes' }" class="execution-node" :class="{ 'execution-node-compact': compact, 'execution-node-attention': attention }" :aria-label="`${node ? name : emptyLabel}，前往节点管理`" data-execution-node>
          <Server :size="13" aria-hidden="true" /><span>{{ node ? name : emptyLabel }}</span>
        </router-link>
      </TooltipTrigger>
      <TooltipPortal>
        <TooltipContent class="fui-info-content" side="top" :side-offset="8" :collision-padding="12" @escape-key-down="event => event.stopPropagation()">
          <p>{{ node ? name : emptyLabel }}</p>
          <p v-if="node"><code>{{ node.node_key }}</code><template v-if="node.kind"> · {{ node.kind === 'local' ? '本机' : 'SSH' }}</template></p>
          <p v-if="status">{{ status }}</p>
          <p>点击前往节点管理</p>
        </TooltipContent>
      </TooltipPortal>
    </TooltipRoot>
  </TooltipProvider>
</template>

<style scoped>
.execution-node{display:inline-flex;align-items:center;gap:5px;min-width:0;max-width:100%;color:inherit;font-size:var(--ui-font-small,12px);line-height:1.5;text-decoration:none;}
.execution-node svg{flex-shrink:0;}
.execution-node>span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.execution-node:hover{color:var(--ui-accent,#856b9e);}
.execution-node:focus-visible{outline:2px solid var(--ui-focus,#ad9bc4);outline-offset:3px;border-radius:3px;}
.execution-node-attention svg{color:var(--ui-danger,#b45b67);}
</style>
