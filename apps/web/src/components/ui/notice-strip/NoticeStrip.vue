<script setup lang="ts">
/**
 * 提示条：整行的浅色语义底条，用于兼容结果、维护说明、凭据状态等一句话提示（设计稿 .strip）。
 * @prop tone 语义色：success、warning、danger、info、neutral，默认 neutral。
 * 默认插槽：图标与文字；插槽 end：靠右的徽标或操作。
 */
withDefaults(defineProps<{ tone?: 'success' | 'warning' | 'danger' | 'info' | 'neutral' }>(), { tone: 'neutral' });
</script>

<template>
  <div class="fui-strip" data-slot="notice-strip" :data-tone="tone">
    <slot />
    <span v-if="$slots.end" class="fui-strip-end"><slot name="end" /></span>
  </div>
</template>
