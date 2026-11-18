# 同形体任务的当前源码合同

## 依赖与基线

- 当前分支feat/agy-account-runtime，HEAD 37aa1399，运行环境业务提交c61d635b；账号与凭据来自f2d9c4c6。
- 当前任务为既有planning子任务，主要实现归属gateway和orchestrator；账号UI使用apps/web。
- 真实外部生成预算0。系统基线通过断网容器、UID1001、固定原版及本地TLS完成，9次合成原生提交。摘要为native-system-baseline.json。

## 已定义字段及入口

- services/gateway/src/model/account.rs及service/agy_account.rs保存并更新agy_system_prompt_homoglyph_enabled；默认false。
- apps/web/src/components/Accounts.vue:111、:357、:453、:1236已包含默认值、编辑回读、更新载荷和开关；文案当前为“按当前账号保存，将在模型服务接入后生效。”。
- services/gateway/src/service/agy_contract.rs的AgySubmission使用deny_unknown_fields，当前无策略字段。AgyToolCompletion只负责原工具收口。
- services/gateway/src/service/gemini.rs准入后读取current Account，提交原始body；drive在认证恢复重用body。新增策略须同一次冻结并显式传入恢复。
- services/orchestrator/agy_runtime/supervisor.py的validate_submission按字段集合严格校验。worker_key包含凭据、模型、代理及采集策略，文本策略应按请求传递以复用暖worker。
- gemini_contract.decode_request从systemInstruction.parts[].text生成独立system，保留gemini_body及native_steps；Kernel.execute写入cascadeConfig.plannerConfig.declarativeMixinConfig.promptSections[].custom.content。
- 固定原版实际本地TLS请求为request.systemInstruction.parts[].text。开启工具与普通文本时该段均与输入系统文本一致，转换可限定在独立system上。
- 现有request_accepted、input-mapping.json、gemini-input.json及rpc.ndjson可以承接策略和原始/提交视图区分；完整请求页面属于后续子任务。

## 参考规则

- 只读来源/root/project/new-api/scripts/system-prompt-worker/src/index.mjs:11-16，26个固定ASCII到同形Unicode映射。
- 同目录test/worker.test.mjs:252起验证“ABC system 中文 {x: 3}”到“ΑΒС ѕуѕtеm 中文 {х: 3}”，包含整包/分块及再次经过一致性。
- 参考Worker同时具有用户星号、零宽字符和其他协议处理；本任务只引用固定同形表。new-api及其渠道配置保持外部范围。
- 完整文件SHA与映射保存在reference-mapping.json。转换后码点不属于源键，幂等成立；UTF-8字节数和模型token数是独立口径。

## 验证边界

原生TLS基线只证明现有系统段构造和输入映射；策略转换将在实施后独立验收。合成上游返回的usage/cache验证字段保真，真实模型分词、缓存和计费影响由后续有授权账号及独立预算的验收承接。用户人工Google登录保持后续条件。
