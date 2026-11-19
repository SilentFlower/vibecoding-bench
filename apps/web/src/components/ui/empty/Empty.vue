<script setup lang="ts">
/** 空态：图标块、标题、说明与操作，用于列表或卡片区无数据时。 */
defineProps<{ title: string; description?: string }>();
</script>

<template>
  <div class="fui-empty-state" data-slot="empty">
    <div v-if="$slots.icon" class="fui-empty-state-icon" aria-hidden="true"><slot name="icon" /></div>
    <p class="fui-empty-state-title">{{ title }}</p>
    <p v-if="description" class="fui-empty-state-description">{{ description }}</p>
    <div v-if="$slots.actions" class="fui-empty-state-actions"><slot name="actions" /></div>
  </div>
</template>
