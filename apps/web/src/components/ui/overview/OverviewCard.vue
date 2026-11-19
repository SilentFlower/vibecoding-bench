<script setup lang="ts">
import { IconTile, type IconTileTone } from '../icon-tile';

/**
 * 概览卡：标签、大号等宽数值、一行说明，右上角图标块。
 * @prop label 标签。
 * @prop value 数值；value 插槽可替换为自定义内容。
 * @prop unit 数值后的小号单位或分母（如「/ 21」）。
 * @prop caption 说明；caption 插槽可覆盖。
 * @prop tone 图标块语义色，默认主色。
 * 插槽 icon：图标块内的图标。
 */
withDefaults(defineProps<{ label: string; value?: string | number; unit?: string; caption?: string; tone?: IconTileTone }>(), { tone: 'primary' });
</script>

<template>
  <article class="fui-overview-card" data-slot="overview-card">
    <div class="fui-overview-card-body">
      <p class="fui-overview-card-label">{{ label }}</p>
      <strong class="fui-overview-card-value"><slot name="value">{{ value }}</slot><small v-if="unit">{{ unit }}</small></strong>
      <span v-if="caption || $slots.caption" class="fui-overview-card-caption"><slot name="caption">{{ caption }}</slot></span>
    </div>
    <IconTile v-if="$slots.icon" :tone="tone"><slot name="icon" /></IconTile>
  </article>
</template>
