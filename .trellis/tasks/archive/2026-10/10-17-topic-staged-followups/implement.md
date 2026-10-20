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

runner 的终点为本地代码提交与任务 Close；随后根据本次用户授权按 `release.md` 连续执行普通 Git 推送、GitHub Actions 联合镜像发布、v3 空闲停机、兼容迁移、部署与验收；最新用户指令禁止新增服务器备份。该阶段不额外创建功能范围或改变账号配置；线上模型请求不在授权验证范围。

## 实际验证证据（代码交付前）

- 后端全量 313 项通过，随后题库/JSON 长度边界 12 项、英文内容 6 项、额度恢复 38 项定向复核通过；重复覆盖不累计测试数。部署工具 32 项通过。
- 本地联合镜像 `followups-20261017-local` 已完成正式 Dockerfile 构建；角色隔离、原生 TLS 转发、API 长流/CLI 并行、同 run 恢复、网络失效及重建断言通过。完整演练曾因测试替身未规范化粘贴回车、以及认证错误样例缺少 error 字段而失败；修正替身后 `--followups-only` 退出 0，实际 driver/tmux 的 0/1/2 次追加及认证失败即停止逐条核对通过。
- `verify_stack.py --browser --topic-followups` 退出 0：真实浏览器编辑、API/SQLite、旧运行冻结正文、2/2 阶段、XSS 转义和 1280/390px 明暗主题通过。
- 已只读核对原生 CLI 2.1.293 的版本及线上历史主会话 JSONL 字段形状；未进行真实模型推理或新的登录/付费调用。600 题结构与语义审查不冒称全部模型实跑。
- `sync-topics-db.py --validate-only`、Python 编译、shell/JS 语法、`git diff --check` 均通过。原 55 条 protected-retained 在提交前再次按 runner 摘要核对。
- [上线后验证] 推送与 Actions 同批清单、空闲停机备份、schema/题库同步、原 topic ID/历史 prompt/持久 HOME 核对及健康验收，按 release.md 继续；本地通过不代表已经上线。

## 2026-10-17 返工计划

1. [x] 修复真实 pasted_content 包装匹配，保留严格正文/主会话校验与旧阶段兼容。
2. [x] 修复 no-next 下缺少阶段证据的等待，收尾回复完成后立即退出并报告补充未完成。
3. [x] 默认改为 literal 按键输入及 Ctrl+J 换行，覆盖多行、特殊字面文本、单次提交及 Tab/CR 兼容。
4. [x] 增强替身对按键/粘贴及真实包装的建模，通过阶段机与实际 driver/tmux 回归。
5. [x] 按 follow-up-edit 的 Pre-Check hold 完成针对性验证后交还用户；下一步按 owner 进入 Check-All、规范与发布链。

## 返工针对性验证结果

- 阶段/冻结 16 项、worker 启动/按键 6 项、额度 38 项分别通过，共 60 项，未累计上一轮覆盖。
- 原生 CLI 2.1.293 在断网、独立 HOME 与合成 localhost SSE 下通过真实产品按键函数完成初始及一条补充；两条输入正文/换行、原会话、阶段完成核对通过，均无粘贴包装。结果 `/tmp/topic-followups-native-evidence/native-input.json`，未使用生产账号或真实模型。
- 同源正式本地联合镜像 `/tmp/topic-followups-fix-local.json` 完成构建；`--followups-only` 重跑退出 0，0/1/2 条补充及认证失败场景通过。已识别输入和未知包装两种收尾均在真实收尾信号后约 4.5 秒以 124 退出，状态明确业务补充未完成；原计划及输入证据保留。
- 首次演练的收尾时限断言包含约 25 秒 TUI 启动等待而失败；未改产品预算，改为从真实收尾 marker 计时并核对明确状态后，全部六场景通过。初次日志 `/tmp/topic-followups-fix-docker.log`，成功日志 `/tmp/topic-followups-fix-docker-rerun.log`。
- 实际 Docker 三角色权限/只读根/秘密隔离、系统信息边界、真实网关本地 TLS 与错误绑定无重放的既有前置断言通过。所有临时演练容器与网络已由 runner 清理。
- shell 语法、Python 编译和 diff 空白检查通过，原 55 个非本任务文件内容摘要保持，cc2api 子仓干净。本次返工未提交、未部署；保持 Pre-Check hold，等待用户下一步进入完整检查。

## Check-All 修复批次

- 发现并报告 CHK-001（混合 thinking/text 回复被漏判）和 CHK-002（原生 CLI 异步落盘顺序被当作对话顺序），用户已要求修复全部。
- [x] 统一主会话解析与完成检测，分开 user 严格输入确认和 assistant 混合正文提取。
- [x] 在原 byte cursor 范围内按父链及时间恢复顺序，排除异根与坏链；旧无时间记录兼容。
- [x] 同步两个镜像的模块入口与实际消费者测试，回归两个失败场景及原生 CLI 快速响应。
- [x] 完成定向验证后直接返回当前 Check-All 重检，不重新进入 Pre-Check hold；通过后继续规范与提交 owner。

## 本批修复重检证据

- 当前代码后端全量 324 项、部署工具 32 项通过，日志为 `/tmp/topic-followups-fix3-backend.log`、`/tmp/topic-followups-fix3-deploy.log`；阶段用例包含混合正文、0/1/2 乱序阶段、附件父链、倒序时钟、旧执行基线、异根和坏链。
- 原生 CLI 2.1.293 在断网容器、UID1000、独立 HOME、合成 localhost SSE 下完成两轮真实按键输入。多行及行尾反斜杠保持，两次通用完成分类均为 complete，阶段依次 send/complete，恢复复核通过。结果 `/tmp/topic-followups-native-evidence4/result.json`；该次实际落盘为 user/assistant 顺序，另将原生全部字段及附件按回复先写重放，两个消费者也通过，日志 `/tmp/topic-followups-native-replay.log`。
- 正式 Dockerfile 联合构建 `followups-fix-20261017-d` 成功，清单 `/tmp/topic-followups-fix4-local.json`。account 模块/命令链接及 control driver 与当前源码逐字节一致。早先 c 批次在 HEV 下载时网络失败；d 批次使用已关闭的临时构建代理完成，不修改产品网络配置。
- `run_local_verification.py --manifest /tmp/topic-followups-fix4-local.json --followups-only` 退出 0：六场景均使用混合正文、回复先落盘及真实包装；0/1/2 追加、认证失败、两种收尾全部通过。已知和未知输入的收尾均在信号后 4.5 秒以 124 退出，保留未完成阶段。配套三角色隔离和本地 TLS 转发断言通过，演练容器与网络清理完成。
- Python 编译、shell/JS 语法、600 题校验、diff 空白检查通过；55 个非本任务文件摘要未变，cc2api 子仓干净。CHK-001/CHK-002 均修复，当前仅本地验证，尚未提交或部署。

## 随机时间投递调整计划

- 上一修复批次已通过 Actions `39001123244` 并部署 `ci-39001123244-1`；管理桥、阶段 API、原活动账号新镜像与 11,880 个持久条目核对通过。本次调整已完成实现和针对性验证。
- [x] 只读核对 `c9e86e2bb10a`：首条输入已匹配，主会话持续工具执行，无正常 end-turn；0 条补充由旧的“等回复再发”设计造成，非旧包装识别问题。
- [x] 在断网容器、独立 HOME、合成 SSE 与原生 2.1.293 下实证忙碌中两条按键投递、enqueue、合并消费和同一最终回复；未使用生产账号或真实模型。
- [x] 用户选择 10%～60% 随机窗口，完成时间快照、旧记录兼容与恢复契约的增量设计。
- [x] 更新所有新 run 创建及恢复 payload，新增消息到点调度，与完成判定分离；旧 run 保持已保存模式。
- [x] 同步运行详情的计划/投递/消费/完成状态和定向测试，覆盖提前空闲、忙碌入队、合并消费、延迟确认、pending 重启与硬门禁。
- [ ] 实际 driver/tmux 与原生 CLI 忙碌演练后按当前 follow-up-edit owner 完成定向验证，再进入检查、规范、精确提交及部署；部署不再新增大体积备份。

## 随机时间投递：最终针对性验证

- 用户已选择 10%～60% 窗口。本轮业务实现完成，未提交/推送/部署。用户“下一步”已清除 `follow-up-edit` hold；完整检查复现 FBK-001 / FBK-002 两项异常分支问题；用户选择修复全部后，两项均已修复并通过定向重检。
- 后端全量 330 项通过（`/tmp/topic-followups-timed-backend.log`）；随后补充乱序父链与 CLI 无效时间快照 2 项，并在最终代码上通过题库/冻结/阶段共 29 项（`/tmp/topic-followups-timed-final-unit.log`）。后者包含前者覆盖，不能累计冒称全量 359 项。部署工具 32 项通过（`/tmp/topic-followups-timed-deploy.log`）。
- 原生 CLI 2.1.293、断网容器、独立 HOME、localhost 合成 SSE 与最终 helper 真实联动：计划为 6/12 秒，实际按键提交约 7.13/13.20 秒，两条均在首轮响应返回前入队。入队时无普通 user；随后两条消费、共享一个正常最终回复，completed_stages=3。证据 `/tmp/topic-followups-timed-evidence-d/result.json`，不涉及生产账号或真实模型推理。
- 正式 driver/tmux 演练 c 批次全九场景通过：旧 0/1/2、认证、两种未完成收尾，新定时提前空闲、忙碌入队及认证。收尾分别在 marker 后约 4.6/4.5 秒以 124 退出；日志 `/tmp/topic-followups-timed-driver-c.log`。最终 helper 的 d 批次再用 `--timed-followups-only` 通过三场景，日志 `/tmp/topic-followups-timed-driver-d.log`；两条忙碌补充有相同最终 reply_entry，正文/按键/会话/目录核对通过。
- 最终联合镜像清单 `/tmp/topic-followups-timed-local-e.json` 已构建。helper、命令链接、control driver、main.py、topic_library.py、app.js 均与最终源码逐字节一致；helper SHA256 `b1752df027aa745df2bb6a26a76bb80252e02403ed7a592c02387a677228a7e7` 与 d 演练相同。e 相对 d 仅将新时间计划的短预算收尾间隔由 1 秒增至 5 秒，29 项最终测试包含上界时刻与轮询余量断言，driver/helper 未再变化。
- 浏览器/API/SQLite 演练通过：旧阶段、新计划时间、2/2 投递但 1/2 消费和 0/2 完成的独立显示、共同回复完成、XSS、1280/390px 明暗主题；日志 `/tmp/topic-followups-timed-browser.log`。已查看窄屏暗色和桌面亮色截图，内容可读且弹窗无越界。
- 两镜像构建、实际三角色隔离与本地 TLS 转发前置断言通过；合成测试容器、网络和临时构建代理已收口。Python 编译、shell/JS 语法、600 题校验及 diff 检查通过。55 个非本任务文件摘要保持，cc2api 子仓干净。
- 生产实例、活动运行和账号凭据未操作；没有新增服务器备份。后续按 release.md 的最新无备份部署方案执行。

## FBK-001 / FBK-002 修复批次

用户已选择修复全部。本批只修复已报告的异常恢复和进度保护，不改变随机窗口、消息计划、凭据或部署边界。

1. [x] 已绑定主会话却失去初始输入时，拒绝恢复及推进，保留阶段文件原字节；覆盖已消费、已完成、删除/截断/被其它输入替换和首次等待。
2. [x] 运行中阶段文件缺失时清空确定计数；拒绝空输入/回复证据和缺时钟的已执行阶段；页面显示 unknown/invalid。已排队未开始仍正常展示等待到点。
3. [x] 进行对应单元、真实浏览器及正式镜像/driver 验证，直接返回当前 Check-All 重检，不重新进入修改前暂停。

## FBK 修复验证结果

- FBK-001：已确认主会话而失去初始输入时立即 ValueError，覆盖已消费/已完成、删除/截断/替换及 init/observe/tick；原状态字节保持。未绑定的首次输入允许正常等待。
- FBK-002：运行后的缺文件返回 unknown 和空计数，排队未开始仍为 not_started/零投递；空或空白证据以及已执行阶段缺时钟均为 invalid。页面显示阶段待核对/证据无效，不把未知显示为等待到点或完成。
- 后端全量 336 项通过（/tmp/topic-followups-fbk-backend.log），包含针对性 33 项，不能重复累计。正式镜像 followups-timed-fbk-20261017-a 构建成功，helper/链接、driver、main/topic_library/app.js 与最终源码逐字节一致。
- /tmp/topic-followups-fbk-driver.log 三项实际 driver/tmux 定时场景通过（提前空闲、忙碌两条同回复、认证先停）；/tmp/topic-followups-fbk-native/result.json 的原生 CLI 2.1.293 断网合成 SSE 与真实按键联动通过，不使用生产账号或真实模型。
- /tmp/topic-followups-fbk-browser.log 真实浏览器/API/SQLite 验证通过，包括运行中缺文件、空证据、正常未启动及原有明暗窄屏/XSS；Python 编译、JS/shell 语法、diff 检查通过。55 个无关文件摘要及 cc2api 子仓保持。
- 重检复用原 Full 基线，局部 effective=light，FBK-001/FBK-002 均关闭，无新增 CHK/FBK 或阻断。下一步规范同步后进入精确提交计划；生产验收仍按 release.md，无新增服务器备份。
