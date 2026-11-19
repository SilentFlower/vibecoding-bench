<script setup lang="ts">
/**
 * 数据表卡片：标题与计数、头部工具栏、可横向滚动的表格区、底部分页。
 * 最右操作列给 TableHead / TableCell 加 fui-table-actions 类即可在横向滚动时固定。
 * @prop title 卡片标题（h3）。
 * @prop count 标题旁的等宽计数（如「21 / 21 条」）。
 * 插槽 toolbar：标题右侧的搜索与操作；默认插槽：Table；footer：分页。
 */
defineProps<{ title: string; count?: string | number }>();
</script>

<template>
  <section class="fui-card fui-table-card" data-slot="table-card">
    <header class="fui-table-card-head">
      <h3 class="fui-table-card-title">{{ title }}<small v-if="count !== undefined" class="fui-table-card-count">{{ count }}</small></h3>
      <div v-if="$slots.toolbar" class="fui-table-card-toolbar"><slot name="toolbar" /></div>
    </header>
    <div class="fui-table-card-scroll"><slot /></div>
    <footer v-if="$slots.footer" class="fui-table-card-footer"><slot name="footer" /></footer>
  </section>
</template>
