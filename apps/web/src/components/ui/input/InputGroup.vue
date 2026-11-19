<script setup lang="ts">
import type { HTMLAttributes } from "vue"
import { cn } from "@/lib/utils"

/** 带前后缀的输入框外壳；内部放 Input，整组只画一个聚焦外框。 */
const props = defineProps<{
  class?: HTMLAttributes["class"]
}>()
</script>

<template>
  <div
    data-slot="input-group"
    :class="cn('fui-input-group', props.class)"
  >
    <slot name="prefix" />
    <slot />
    <slot name="suffix" />
  </div>
</template>
