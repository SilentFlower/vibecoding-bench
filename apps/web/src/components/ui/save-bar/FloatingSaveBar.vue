<script setup lang="ts">
/**
 * 浮动保存栏：吸附在表单底部，显示待保存项数、说明与撤销 / 保存操作。
 * @prop count 待保存项数；为 0 时显示 cleanLabel。
 * @prop hint 说明文字。
 * @prop cleanLabel 无待保存项时的标题，默认「已同步」。
 * 插槽 actions：撤销、保存等按钮（保存按钮可为表单的 submit）。
 */
withDefaults(defineProps<{ count: number; hint?: string; cleanLabel?: string }>(), { cleanLabel: '已同步' });
</script>

<template>
  <footer class="fui-save-bar" data-slot="save-bar" :data-dirty="count > 0">
    <b class="fui-save-bar-title">{{ count > 0 ? `${count} 项待保存` : cleanLabel }}</b>
    <span v-if="hint" class="fui-save-bar-hint">{{ hint }}</span>
    <div v-if="$slots.actions" class="fui-save-bar-actions"><slot name="actions" /></div>
  </footer>
</template>
