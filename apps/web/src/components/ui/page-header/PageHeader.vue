<script setup lang="ts">
/**
 * 页头：标题、一行说明与右侧操作。移动端标题由应用栏显示，这里只保留操作。
 * @prop title 页面标题（h1）。
 * @prop description 说明文字；description 插槽可覆盖（如附加待应用数）。
 * 插槽 actions：右侧操作。
 */
defineProps<{ title: string; description?: string }>();
</script>

<template>
  <header class="fui-page-header" data-slot="page-header" :class="{ 'has-actions': $slots.actions }">
    <div class="fui-page-header-text">
      <h1 class="fui-page-header-title">{{ title }}</h1>
      <p v-if="description || $slots.description" class="fui-page-header-description"><slot name="description">{{ description }}</slot></p>
    </div>
    <div v-if="$slots.actions" class="fui-page-header-actions"><slot name="actions" /></div>
  </header>
</template>
