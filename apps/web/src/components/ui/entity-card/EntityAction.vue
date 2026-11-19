<script setup lang="ts">
/**
 * 实体卡底栏操作：图标 + 文字，按动作数等分底栏；点击事件经属性透传。
 * @prop tone default 为常规，primary 为首要操作，danger 为危险操作。
 * @prop disabled 是否禁用。
 */
withDefaults(defineProps<{ tone?: 'default' | 'primary' | 'danger'; disabled?: boolean }>(), { tone: 'default' });
</script>

<template>
  <button type="button" class="fui-entity-action" data-slot="entity-action" :data-tone="tone" :disabled="disabled"><slot /></button>
</template>
