import type { VariantProps } from "class-variance-authority"
import { cva } from "class-variance-authority"

export { default as Badge } from "./Badge.vue"

// 视觉由 kit.css 的 fui-badge-* 类决定：default 为主色，secondary/outline 为中性，destructive 为危险，另有功能色与平台色。
export const badgeVariants = cva(
  "fui-badge",
  {
    variants: {
      variant: {
        default: "fui-badge-default",
        secondary: "fui-badge-secondary",
        destructive: "fui-badge-destructive",
        outline: "fui-badge-outline",
        success: "fui-badge-success",
        warning: "fui-badge-warning",
        info: "fui-badge-info",
        cc: "fui-badge-cc",
        agy: "fui-badge-agy",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
)
export type BadgeVariants = VariantProps<typeof badgeVariants>
