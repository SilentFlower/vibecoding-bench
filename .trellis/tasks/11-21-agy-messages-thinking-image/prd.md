# 反重力 Messages 兼容思考档位和图片回包

## Goal

让使用反重力 Gemini 的 Claude Messages 客户端能选择思考深度并收到模型实际返回的图片。

## Background

- 上一轮已接通 Flower2API 的 Messages 双向转换与原版 AGY WebSearch。现有 Gemini 入口能按思考参数选择账号目录档位，Messages 入口尚未把 Claude 思考参数交给该路径。
- 合成 AGY 结果验证了源帧投影保留 `inlineData`。当前 Messages JSON 和 SSE 只转换文本、思考和普通函数调用。

## Requirements

- R1. 识别手动思考预算和顶层 `output_config.effort`，优先使用当前令牌可见且可接单的对应档位。目录缺少所需档位时仍可走该基础模型原有的默认选号。显式模型档位和待回填工具轮的原账号、原执行档位具有优先权。
- R2. 将模型实际返回的有效内嵌图片表示为与 Sub2API 相同形状的 Markdown 图片文本。JSON 和 SSE 都保留图片数据、MIME 和原内容顺序。
- R3. 兼容范围在 Flower2API 的反重力 Messages 路径。原版 AGY 搜索、现有鉴权、普通工具回填 ID 和直接 Gemini 入口继续沿原合同验收。

## Acceptance Criteria

- [ ] AC1（R1）用手动预算和自适应 effort 发起请求。实际原生型号符合可用档位。没有匹配档位及无有效思考参数的请求仍能使用原目录默认。显式型号可重复选择。
- [ ] AC2（R1、R3）在带思考签名的工具调用后使用不同 effort 回填。上游仍收到原账号和原执行型号的工具结果。普通多轮、直接 Gemini 请求和 AGY WebSearch 回归通过。
- [ ] AC3（R2）用固定版 AGY 的隔离回环返回文本、图片、文本和终态。对照 Claude JSON 和 SSE 拼接结果核对原顺序、MIME、图片字节和完成事件。异常图片数据有可区分的行为。
- [ ] AC4（R2）真实出图的验证记录固定 AGY 版本、授权测试环境、账号可用模型和真实图片回包。环境或能力待验证时，交付证据标明本轮图片回包为合成上游联调。

## Out of Scope

- 精确 token 控制和主动启用图像生成属于原生模型及发送器的能力工作。当前发送器的显式输出模式为 `TEXT`。该接口的图片兼容面向 AGY 返回的真实图片 Part，实际出图能力以 AC4 为准。
- New API、ACP、部署换版与其它 Sub2API 兼容字段属于独立范围。
