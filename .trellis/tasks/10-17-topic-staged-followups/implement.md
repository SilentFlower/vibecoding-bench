# 实施计划

## 门禁与范围

- [x] 完成三件套、上下文与 Brief，交由当前 schema 2 auto-loop prepare 审核和激活；遵循 inline 个人偏好。
- [x] 只认领本任务文件与实际功能文件，保留原 55 个非本任务改动；不修改 cc2api 子仓。

## 实施顺序

1. [x] 核对并扩展题库解析/校验/同步契约和兼容 schema；记录相关实体与字段，先打通正式题库两条补充和历史零补充。
2. [x] 逐分类重构全部 600 个英文题目和 1,200 条补充；替换 LLM/外部输入/不合范围条目，维护审查清单及跨分类样例；保留完整编号和分类块计数。
3. [x] 扩展 Topic API/编辑、task/batch item 候选冻结及所有 run 创建事务里的随机计划；规范/自定义/历史单轮，重复运行各抽一次；quota 恢复只读旧计划。
4. [x] 实现标准库阶段机与跨尝试证据文件，接入 worker 的真实完成边界、投递和输入确认；调整 v3 私有映射和镜像 COPY，保留单轮、退出、认证、停止与额度语义。
5. [x] 增加运行详情的消息计划及阶段状态，页面仍全自动；确认 XSS、坏状态与旧记录显示。
6. [ ] 执行有意义的针对性验证，再进入完整 Check-All；发现问题通过 runner fix/recheck，最后更新权威规范并精确本地提交。

## 验证命令及证据

使用 `/tmp/v3-unbind-venv/bin/python`（已安装后端依赖）执行相关 unittest；扩展后记录实际测试数，不重复计数。

```bash
/tmp/v3-unbind-venv/bin/python -m unittest discover -s orchestrator -p 'test_english_content.py'
/tmp/v3-unbind-venv/bin/python -m unittest discover -s orchestrator -p 'test_worker_startup.py'
/tmp/v3-unbind-venv/bin/python -m unittest discover -s orchestrator -p 'test_*.py'
/tmp/v3-unbind-venv/bin/python -m unittest discover -s deploy/v3 -p 'test_*.py'
python3 scripts/sync-topics-db.py --validate-only --topics topics.md
bash -n images/worker/entrypoint.sh
node --check webui/app.js
git diff --check
```

- [x] 新 helper 的恢复/确认/损坏矩阵与实际 tmux 多轮替身演练，必须有收到消息及主会话证据，不能只看模拟状态。
- [x] 同源正式 Dockerfile 的本地联合构建、现有 v3 生命周期/转发/隔离验证及新增 0/1/2 轮验证。
- [x] 页面实际查看题库两条补充和任务阶段；历史/规范/自定义任务保持兼容，记录浏览器与 API/DB 核对结果。
- [x] 全量题目人工语义审查覆盖及禁止主题/自启动规则验证，避免用关键词命中代替审查。

## 关键风险

运行中消息与 tmux/JSONL 之间没有原子事务；不确定状态明确失败。首轮旧回复不能越过阶段游标触发多次追加。每次执行总超时不随补充重置，现有 quota 恢复时限不在本次扩展。活动生产任务自然排空后再升级，避免恢复旧输入时获得新补充。

## 交付后流程

runner 的终点为本地代码提交与任务 Close；随后根据本次用户授权按 `release.md` 连续执行普通 Git 推送、GitHub Actions 联合镜像发布、v3 空闲停机备份和题库同步、部署与验收。该阶段不额外创建功能范围或改变账号配置；线上模型请求不在授权验证范围。

## 实际验证证据（代码交付前）

- 后端全量 313 项通过，随后题库/JSON 长度边界 12 项、英文内容 6 项、额度恢复 38 项定向复核通过；重复覆盖不累计测试数。部署工具 32 项通过。
- 本地联合镜像 `followups-20261017-local` 已完成正式 Dockerfile 构建；角色隔离、原生 TLS 转发、API 长流/CLI 并行、同 run 恢复、网络失效及重建断言通过。完整演练曾因测试替身未规范化粘贴回车、以及认证错误样例缺少 error 字段而失败；修正替身后 `--followups-only` 退出 0，实际 driver/tmux 的 0/1/2 次追加及认证失败即停止逐条核对通过。
- `verify_stack.py --browser --topic-followups` 退出 0：真实浏览器编辑、API/SQLite、旧运行冻结正文、2/2 阶段、XSS 转义和 1280/390px 明暗主题通过。
- 已只读核对原生 CLI 2.1.293 的版本及线上历史主会话 JSONL 字段形状；未进行真实模型推理或新的登录/付费调用。600 题结构与语义审查不冒称全部模型实跑。
- `sync-topics-db.py --validate-only`、Python 编译、shell/JS 语法、`git diff --check` 均通过。原 55 条 protected-retained 在提交前再次按 runner 摘要核对。
- [上线后验证] 推送与 Actions 同批清单、空闲停机备份、schema/题库同步、原 topic ID/历史 prompt/持久 HOME 核对及健康验收，按 release.md 继续；本地通过不代表已经上线。
