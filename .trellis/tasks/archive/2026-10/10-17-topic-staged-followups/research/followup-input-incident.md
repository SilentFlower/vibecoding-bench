# 线上输入包装与收尾等待复盘

## 事实与根因

- 只读检查 `15b4082d2c9d`：run 计划两条，题目 Capacity Estimator。主会话首条 user 为原 prompt 外加完整同 ID 的 pasted_content 包装，内文完全相同；原 helper 直接比较整段字符串，未确认输入，阶段为 awaiting/0。
- 09:32 已有正常 assistant 最终文本；09:40 的通用完成分类为 complete，补充状态仍为 awaiting/0，run 仍 running。driver 在补充 helper 返回 wait 后继续循环。
- 进入收尾后，原 helper 只有认出当前输入及回复才能返回 incomplete；缺少输入时提前返回 wait，因而仍等待硬超时。这是状态机在禁止新阶段时未覆盖的路径。
- 原替身只记录无包装 user 正文；既有只读 CLI 核对覆盖了字段形状，没有覆盖粘贴传输对正文增加的包装。测试通过不代表该输入边界已验证。
- 后续只读确认：该生产 run 于 09:41:35 按旧代码硬超时结束，status=timeout、exit_code=124，未改其状态或向其补发需求。

## 修复与防回归

- 仅接受完整正文或已观察到的单层同 ID 包装；不使用子串/模糊匹配，额外正文和错 ID 不得确认。完成复核与恢复复用同一匹配规则，不改原正文/摘要或已保存计划。
- no-next 下缺少阶段输入或回复明确 incomplete；init/observe 仍只观察，投递不确定重启继续拒绝，不重发。driver 的认证、额度和最终回复门禁不变。
- 按用户增量决定，默认逐行 literal 按键输入、Ctrl+J 换行、末尾一次 Enter；Tab/CR 兼容输入保留括号粘贴，避免文本被快捷键改变。快速输入仍可能被 CLI 包装，不能以更换传输方式替代解析修复。
- 持久回归：真实包装的 string/text-block、初始/两条补充/恢复/最终复核；额外正文、错 ID、截断和并列包装拒绝；no-next 未识别与 pending 缺证据；真实 shell 输入保持原文和仅提交一次。

## 验证证据

- 阶段/冻结回归 16 项、worker 启动/按键回归 6 项、额度 38 项均通过，共 60 项；重复覆盖不累计。
- 原生 Claude Code 2.1.293 使用本次真实 inject_tmux_prompt，在 `--network none`、独立 HOME、UID1000、合成 API Key 与 localhost 合成 SSE 下完成初始及一条补充。两条主输入、多行原文、同一会话与阶段完成均核对通过，两条输入均未被 CLI 包装。没有使用生产账号、OAuth 或公网模型推理。
- 原生验证脚本 `/tmp/topic-followups-native-input.py`，结果 `/tmp/topic-followups-native-evidence/native-input.json`，日志 `/tmp/topic-followups-native-input.log`。官方换行说明：[Interactive mode](https://code.claude.com/docs/en/interactive-mode#multiline-input)，Ctrl+J 不要求终端配置。
- 本地同源联合镜像清单 `/tmp/topic-followups-fix-local.json`；正式 driver/tmux 替身演练同时模拟粘贴包装和键盘传输，不能替代上条原生 CLI 验证或声称生产已升级。
- 正式 driver 六场景已通过：0/1/2 条补充、认证失败、已识别首轮的收尾、未知包装的收尾。后两者分别在收尾信号后 4.5 秒退出，均保留未完成状态；成功日志 `/tmp/topic-followups-fix-docker-rerun.log`。

## 缺陷复盘：混合正文与异步落盘

### 1. 根因类别

- E（隐含假设）与 B（跨层契约）：helper 假设 assistant 全部块均为 text，通用完成检测则允许 thinking/text；两处还将 JSONL 物理顺序当作对话顺序。
- D（验证缺口）：早期替身只写纯文本且严格 user→assistant；只读字段核对未证明实际异步落盘顺序。

### 2. 为何前次修复未覆盖

1. pasted_content 修复解决了线上已证实的输入包装，但不覆盖 assistant 的混合内容和落盘时序。
2. 完成检测和阶段机各自解析同一主会话，允许正常回复的条件发生分歧；单独通过无法证明两个消费者会共同推进。
3. 本轮原生探针首次借用旧 b 镜像时，分类器导入的是旧空模块，报 ImportError；随后将当前模块明确挂载用于源码探针，并用全新正式镜像逐字节核对分发及六场景演练，未将首次失败当作产品已通过。

### 3. 防回归措施

| 优先级 | 机制 | 措施 | 状态 |
| --- | --- | --- | --- |
| P1 | 共用解析 | 两个消费者共用 read_dialogue/latest_dialogue，user 严格匹配，assistant 独立排除工具与合成错误 | 已实现 |
| P1 | 对话归属 | 通过 UUID/parentUuid、附件父链和时间恢复顺序，保留原字节 cursor；坏链拒绝，异根不完成 | 已验证 |
| P1 | 实际组合 | 相同记录同时验证 classifier 与阶段机；六个正式 driver 场景都模拟混合正文和乱序 | 已通过 |
| P1 | 原生格式 | 原生 2.1.293 两轮按键输入及真实记录乱序重放；正式镜像验证模块与源码一致 | 已通过 |

### 4. 系统性核对

- 通用完成检测覆盖零补充路径，阶段机覆盖有补充及恢复；两个镜像同步模块路径，保留原命令链接。
- 旧无 UUID/时间记录仍按旧格式兼容；字节基线、旧回复隔离、合成认证/额度错误及 no-next 不完整收口均保留。
- 原生该次实录为顺序落盘，乱序结论由先前原生发现、真实记录重放和持久回归共同支持；没有真实模型或生产账号探测。

### 5. 知识沉淀

- 在现有题库阶段契约中记录输入包装、内容块、父链顺序、稳定窗口、字节边界和收尾错误矩阵。
- 在现有 worker 完成契约中明确共用模块分发与逻辑最新消息，避免再维护不同解析规则。
- 本批验证明细见 implement.md 的“本批修复重检证据”；临时证据路径是当次验证记录，不是可长期依赖的发布产物。
