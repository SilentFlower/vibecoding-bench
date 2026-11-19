import type { Component } from 'vue';

/** 分段选项；count 显示在文字右侧，icon 显示在文字左侧。同组 value 必须唯一。 */
export interface SegmentedOption {
  value: string;
  label: string;
  count?: number;
  icon?: Component;
  disabled?: boolean;
}
