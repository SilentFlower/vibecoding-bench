# 原生附件消费证据与测试缺口

## 只读线上核对

2026-10-17 核对运行 8bd1831f4dce，旧批次 ci-39010558095-1。时间均为北京时间；只读数据库、状态和会话，没有发消息、重跑或调用模型。

- 初始输入时钟 16:58:41.028；一条补充，时间 schema 1，目标 279 秒。
- 17:03:22.584：精确正文 enqueue。17:03:48.191：同正文 remove，随后原生附件落盘，附件时间仍为 enqueue 时间，不能以时刻/物理顺序代替父链。
- 附件顶层 type=attachment，带 uuid/parentUuid、sessionId、isSidechain=false；attachment 有 type=queued_command、字符串 prompt、source_uuid、delivery_id、commandMode=prompt、origin.kind=human、humanTurn=true、timestamp。
- rendered 是渲染文本数组及系统提醒包装，不是消费确认的权威正文入口。
- 17:14:44.759 正常 end_turn 明确确认实现中途追加的出行缓冲与不可达行程提示；17:18:52.658 收尾再次确认。两条均能沿父链追溯到附件。
- 阶段 schema 2 为 awaiting、completed_stages=1、item=queued，仅有 queue_entry，无 input_entry/reply_entry。
- 17:19:05.858：timeout，错误为“已进入收尾窗口，配置的业务补充尚未全部完成”。

## 当前代码复现

在临时目录，用当前 helper、合成题面和固定时钟写入 user → enqueue → remove → queued_command → end_turn assistant，附件与回复父链正确。

实际 action=wait、item=queued，预期 complete。退出 0 代表复现断言成立，不代表修复通过；临时资料自动删除，真实模型调用 0。

## 原因和边界

read_dialogue 保留了所有 uuid/parentUuid 连接，但未把原生 queued_command 解析为输入事件。定时阶段因此无法确认消费。旧测试及 Docker 替身均写普通 user，覆盖不到真实形状。

拟在公共解析器中归一化严格有效的原生附件，复用正文、字节边界、父链和完成判定；不根据回复“声称完成”或队列 remove 直接推进。

## 修复后的回归与复盘

公共解析器保留原附件字节键和父链，严格核对会话、commandMode、origin.kind与humanTurn，阶段和通用完成消费者共同使用。358项后端、17个driver/tmux场景及浏览器/API/SQLite通过，4个原生场景直接确认input_entry指向queued_command，并观察最终回复前的consumed。

根因为隐含假设和测试覆盖缺口：旧忙碌替身生成普通user，不能证明原生附件适配。预防是同时保留两种实际形状、对仅入队/移除和工具/渲染引用作反向断言，并把字段和恢复约束写入现有权威规范。没有为本任务新增通用思考指南或独立检查报告。
