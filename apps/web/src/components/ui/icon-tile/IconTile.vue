<script setup lang="ts">
import type { IconTileTone } from '.';

/**
 * 图标块：语义色浅底加同色图标，用于概览卡右上角与实体卡头部。
 * @prop tone 语义色，默认主色。
 * @prop size md 为 36px（概览卡），lg 为 40px（实体卡）。
 * 默认插槽：图标。
 */
withDefaults(defineProps<{ tone?: IconTileTone; size?: 'md' | 'lg' }>(), { tone: 'primary', size: 'md' });
</script>

<template>
  <span class="fui-icon-tile" data-slot="icon-tile" :data-tone="tone" :data-size="size" aria-hidden="true"><slot /></span>
</template>
