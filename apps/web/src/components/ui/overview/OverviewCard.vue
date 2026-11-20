<script setup lang="ts">
import { IconTile, type IconTileTone } from '../icon-tile';

/**
 * 概览卡：标签、大号等宽数值、一行说明，右上角图标块。
 * @prop label 标签。
 * @prop value 数值；value 插槽可替换为自定义内容。
 * @prop unit 数值后的小号单位或分母（如「/ 21」）。
 * @prop caption 说明；caption 插槽可覆盖。
 * @prop tone 图标块语义色，默认主色。
 * @prop interactive 为 true 时整卡渲染为按钮（悬停、聚焦环、禁用态），点击由调用方处理，disabled 透传。
 * 插槽 icon：图标块内的图标。
 */
withDefaults(defineProps<{ label: string; value?: string | number; unit?: string; caption?: string; tone?: IconTileTone; interactive?: boolean }>(), { tone: 'primary', interactive: false });
</script>

<template>
  <!-- 按钮内只能放行内内容，可点击形态的正文与标签改用 span，外观由 kit.css 保持一致。 -->
  <component :is="interactive ? 'button' : 'article'" :type="interactive ? 'button' : undefined" class="fui-overview-card" :class="{ 'is-interactive': interactive }" data-slot="overview-card">
    <component :is="interactive ? 'span' : 'div'" class="fui-overview-card-body">
      <component :is="interactive ? 'span' : 'p'" class="fui-overview-card-label">{{ label }}</component>
      <strong class="fui-overview-card-value"><slot name="value">{{ value }}</slot><small v-if="unit">{{ unit }}</small></strong>
      <span v-if="caption || $slots.caption" class="fui-overview-card-caption"><slot name="caption">{{ caption }}</slot></span>
    </component>
    <IconTile v-if="$slots.icon" :tone="tone"><slot name="icon" /></IconTile>
  </component>
</template>
