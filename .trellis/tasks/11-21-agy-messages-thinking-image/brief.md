# Brief — 反重力 Messages 兼容思考档位和图片回包

## Goal

- 让使用反重力 Gemini 的 Claude Messages 客户端能选择思考深度并收到模型返回的图片。

## Scope

- 在 Flower2API 接入 Claude 的手动思考预算和 `effort`。
- 将 AGY 返回的内嵌图片转成 Claude JSON 与 SSE 可传递的 Markdown 文本。

## Non-Goals

- 精确 token 控制、主动启用图像生成、New API 与 ACP 接入、部署换版属于独立工作。

## Technical Overview

- `/v1/messages` 把受支持的思考参数交给现有 Gemini 选号。相同的图片格式规则用于流式和非流式响应，保留 MIME、图片数据和顺序。[Claude 思考参数](https://platform.claude.com/docs/en/build-with-claude/effort) · [Sub2API 图片回包](https://github.com/Wei-Shaw/sub2api/blob/v0.2.24/backend/internal/pkg/antigravity/response_transformer.go)

## Context & Decisions

- **【关键决定】优先选择目标档位。目录缺少该档位时使用同一基础模型原有的可用档位。**
- **【关键决定】工具回填使用原账号和原执行档位，保留调用 ID 和思考签名。**
- **【重要限制】思考 token 数由所选 AGY 型号决定。图片展示取决于客户端的 Markdown 渲染。**

## Risks

- **【交付风险】当前发送器只接受 `TEXT` 输出模式。真实出图需用固定 `agy 1.5.9` 和获授权账号的目标模型验证。** 隔离回环可验证返回图片时的协议转换。

## Acceptance

- 核对预算、effort、显式档位和目录缺档时实际发往原生的型号。用不同 effort 回填时核对原账号和原档位。
- 使用实际二进制与合成上游，核对 JSON 和 SSE 的图片字节、文本顺序及终态。回归普通工具、直接 Gemini 入口和原版 AGY WebSearch。

## Next Step

- 在 Messages 请求转换中接入现有思考档位选择。
