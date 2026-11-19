import type { VariantProps } from "class-variance-authority"
import { cva } from "class-variance-authority"

export { default as Button } from "./Button.vue"

// 视觉由 kit.css 的 fui-button-* 类决定；旧变体名保留：outline/secondary 为次要填充，ghost 为文字，destructive 为危险浅底。
export const buttonVariants = cva(
  "fui-button",
  {
    variants: {
      variant: {
        "default": "fui-button-default",
        "destructive": "fui-button-destructive",
        "outline": "fui-button-outline",
        "secondary": "fui-button-secondary",
        "soft": "fui-button-soft",
        "ghost": "fui-button-ghost",
        "destructive-ghost": "fui-button-destructive-ghost",
        "link": "fui-button-link",
      },
      size: {
        "default": "",
        "sm": "fui-button-sm",
        "lg": "fui-button-lg",
        "icon": "fui-button-icon",
        "icon-sm": "fui-button-icon fui-button-sm",
        "icon-lg": "fui-button-icon fui-button-lg",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
)
export type ButtonVariants = VariantProps<typeof buttonVariants>
