<script setup lang="ts">
import type { HTMLAttributes } from 'vue';
import { ref } from 'vue';
import { TooltipProvider, TooltipRoot, TooltipTrigger, TooltipPortal, TooltipContent } from 'reka-ui';
import './controls.css';

/** 只读说明气泡；原生dialog内传入portalTarget以保持正确焦点层级。 */
interface Props {
  label: string;
  title?: string;
  portalTarget?: HTMLElement | string;
  delay?: number;
  contentClass?: HTMLAttributes['class'];
}
withDefaults(defineProps<Props>(), { delay: 150 });
const open = ref(false);

/** Escape仅关闭当前说明层。@param event 键盘事件。@return 无。 */
function closeOnEscape(event: KeyboardEvent): void {
  event.preventDefault();
  event.stopPropagation();
  open.value = false;
}
</script>

<template>
  <TooltipProvider :delay-duration="delay">
    <TooltipRoot v-model:open="open" disable-closing-trigger>
      <TooltipTrigger type="button" class="fui-info-trigger" :aria-label="label" @click="open = true">
        <slot name="trigger">{{ label }}</slot>
      </TooltipTrigger>
      <TooltipPortal :to="portalTarget">
        <TooltipContent class="fui-info-content" :class="contentClass" side="top" align="start" :side-offset="8" :collision-padding="12" @escape-key-down="closeOnEscape">
          <h3 v-if="title" class="fui-info-title">{{ title }}</h3>
          <slot />
        </TooltipContent>
      </TooltipPortal>
    </TooltipRoot>
  </TooltipProvider>
</template>
