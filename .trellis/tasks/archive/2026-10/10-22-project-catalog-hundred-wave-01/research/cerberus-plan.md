# Cerberus场景任务表

> 状态说明：本文保留设计阶段记录，实际验证与准入以[本项目准入记录](cerberus-admission.json)为准。

固定提交83f5dada76aa3179ef21b677a7f4235bf20c1566，许可证为ISC。已读`validator.py`真实构造选项、规范化顺序、coerce/default/nullable处理、validate/validated/normalized、未知字段处理与dependencies；完整247主项中246通过、1项Python2专用跳过。嵌入的cerberus/tests保持原件并作为受控测试根，候选不能替换测试。

| 任务 | 实际业务价值与事实 | 授权与独立验收 |
| --- | --- | --- |
| CB-U01 理解 | 理解validate复制转换及禁用规范化 | 只读，n字符串2与normalizeFalse对照，原输入不变 |
| CB-C01 咨询 | 导入前必须通过完整规则，不拿normalized冒充有效 | 只读，n字符串1可规范化却不满足min2 |
| CB-U02 理解 | 业务缺省保留None／0还是补默认 | 只读，nullable／missing／required实际矩阵 |
| CB-C02 咨询 | 明确未知字段拒绝、丢弃或保留 | 只读，三种已有选项、原输入副本核对 |
| CB-D01 诊断 | 字段消失时先取得schema与实际选项 | 只读，首问不泄露purge，披露和无证据合法收口 |
| CB-U03 理解 | PATCH局部文档仍检查已给字段的依赖 | 只读，update跳required但不跳dependencies；不假定存储记录 |
| CB-P01 方案 | 批导入保存独立逐行错误与文档身份 | 只读，两次真实处理的最新状态与已保存结果，不宣称并发已验 |

四场景七任务，六条原生观察，无强造代码或答案依赖。问答和工程增强分开；本仓当前任务可以由已有API满足，不制造修改目标。正式注册仍需全部产品链与页面、API、SQLite和Git／Docker独立交付证明。
