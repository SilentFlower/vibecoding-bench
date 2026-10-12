# 实现与验证进度

## 授权与基线

- 用户已确认完整 Brief，task.py start 成功，任务 in_progress。
- implement=inline，来源 route-prefs；当前任务的会话路由已持久化。
- 父仓 v3 基线 8d723cb3cacc43edc88736c292435ad165203bbf，子仓 v3 基线 5af0c9f1d32e93245836d2a280fb6dd148499515；原有 22 项脏文件保留。
- 本轮只本地开发和合成验证，未操作旧服务器服务、真实账号、Git 提交/推送或镜像发布。

## 已实现

- 两个 nullable INTEGER 阈值、StrictInt 请求字段、范围校验、省略保留/null 关闭和同事务保存；账号摘要展示养号判定。
- quota_protocol 增加独立阈值/周期判定，保持 sidecar 副本同步；部分窗口更新不会给仍未知的另一窗口重发机会。
- QuotaGuard 持久单次许可、实际启动/恢复/触发门禁；阈值不会制造共用 exhausted。控制补证校验当前 run/source 及 Recorder 私有文件，拒绝普通作业伪造阈值豁免。
- Recorder 养号作用域、持久首次请求标记、已接受流跟踪与定期共享状态检查。响应回调后仍等待 flow.live=False，再发暂停信号；当前请求未结束时只写 draining 标记，worker 不按后续局部拒绝提前退出。
- worker 读取当前来源的收尾标记，永久认证错误和总超时继续优先；43/原会话保存链路复用。
- 账号养号弹窗增加独立开关/整数输入及已用/剩余说明，账号状态展示阈值和等待，静态资源版本同步。

## 已有证据

- 初始默认行为回归：132 个 orchestrator 测试通过，日志 /tmp/v3-warmup-baseline-tests.log；11 个既有 Recorder 测试通过，日志 /tmp/v3-warmup-recorder-baseline.log。后续源码已变化，不将它们作为最终证据。
- 新增养号测试最初因导入既有 TestCase 被重复收集，已改为模块引用；修正后 14 个新增测试通过，日志 /tmp/v3-warmup-new-tests-final.log。
- 增加更多重启/身份/worker 场景后，/tmp/v3-warmup-policy-tests.log 保留 1 次失败：测试误以为既有身份变化终态为 stopped，实际 _cancel_changed_identity 契约为 auth_failed；已核对原代码并修正测试，未改身份终态行为。待复核新增 19 项。
- 18 个 Recorder 测试（含 7 个养号收尾场景）通过，日志 /tmp/v3-warmup-recorder-tests.log；随后补充 draining 标记，需复核。
- webui/app.js 的 node --check 通过。
- mitmproxy 11.1.3 官方源码确认 response 回调先于发送完整缓冲响应、flow.live 在发送结束后清除：[HTTP 层](https://github.com/mitmproxy/mitmproxy/blob/v11.1.3/mitmproxy/proxy/layers/http/__init__.py)。因此单凭 response 回调不能提前停止 Recorder。

## 后续步骤

- 完整 Check-All 重检通过，CHK-001 已修复，剩余 CHK/FBK 为 0；Update-Spec、提交/发布/部署尚未执行，不宣称线上交付完成。

## 本地镜像与 HTTPS 验证

- 联合批次 local-warmup-20261013-a 构建通过；实际验证先暴露内部网络不发布宿主端口及依赖缓冲日志判断监听的夹具问题，日志 /tmp/v3-warmup-https-a.log、/tmp/v3-warmup-https-a-recheck.log 保留。将测试客户端放入同一无外网网络并使用真实 TCP 就绪检查后，/tmp/v3-warmup-https-a-readiness-recheck.log exit 0。
- 补充控制写入失败和损坏窗口防御：先设置本地拒绝响应，控制写失败不能导致上游请求继续；真实模型候选在共享状态无效时按执行故障拒绝。151 个最新后端与 20 个 Recorder 测试通过，日志 /tmp/v3-warmup-python-b-tests.log、/tmp/v3-warmup-recorder-b-tests.log。
- 此前候选联合批次 local-warmup-20261013-b 构建通过，清单 /tmp/v3-warmup-b.json。/tmp/v3-warmup-https-b.log exit 0：真实镜像 Recorder + 临时受信任本地 HTTPS/SSE，当前流末尾完整到达、后续拒绝、未知实际仅一请求、Recorder 重启不重复、非养号忽略阈值；只创建内部网络/合成凭据，原有本地容器未启停。
- /tmp/v3-warmup-https-b-integrity.log exit 0：相同 B 镜像的正文 SHA256 与完整预期长度匹配，当前响应没有被暂停截断。
- /tmp/v3-warmup-docker-b.log exit 0：固定环境、同 run 第二代 HOME/cwd/resume、共享 API 长流、取消/重启/Recorder 故障、双账号隔离和清理验证通过；CLI 使用明确的测试替身。
- 浏览器首次 /tmp/v3-warmup-stack-browser-b.log exit 1：测试夹具直接写入不支持的 UTC 时区，引发账号列表错误和 alert 阻塞；已读取现有时区契约，仅修正夹具为 Asia/Tokyo。/tmp/v3-warmup-stack-browser-b-timezone-recheck.log exit 0。
- 目视检查发现截图采到主题背景过渡帧；改验证为实际主题按钮切换并等待 120ms 过渡结束，产品 CSS 未改。/tmp/v3-warmup-stack-browser-b-theme-recheck.log exit 0；实际检查桌面/390px 明暗主题、表单滚动及保存按钮可达，截图 /tmp/v3-warmup-form-*.png。
- 文档与 roadmap 已记录本地实现状态。原 22 项脏文件内容完整保留，cc2api 子仓无改动；最新产品源码重算 SHA256 与 B 清单一致。
- 真实官方 CLI/OAuth/实际额度、公网性能、推送、发布及部署未执行；旧服务器服务未操作。
- /tmp/v3-warmup-stack-browser-b-status-recheck.log exit 0：增加实际账号列表阈值/未知等待原因断言后复核通过；这是最终浏览器验证证据。

## 首轮完整检查（修复前）

- requested=auto、effective=full、context=interactive；覆盖当前 27 个文件，原有 22 个脏文件排除且内容未变。
- CHK-001 / P1：update_account_warmup 在 QuotaGuard 锁外发布，旧发布可覆盖并发额度消费的较新文件；_publish 又分别读取共用窗口和养号摘要，产生不一致快照。
- /tmp/v3-warmup-check-publish-race.log：用实际配置接口、临时 SQLite 和线程交错复现 DB 50%、共享窗口 20%、养号摘要命中而 Recorder 重新判定不命中。候选 B 镜像仍含此问题，不能发布为通过批次。
- 补验真实 Recorder error 钩子等待 flow.live 结束、保留单次标记并进入等待，通过；日志 /tmp/v3-warmup-check-error-flow.log。未发现其它独立 CHK/FBK 根因。
- 仅按 DOC 通道更新过期的阶段/验收事实，不修改产品代码、测试、配置或规划语义；修复范围待当前检查报告处置。

## CHK-001 修复与重检

- 用户明确要求“修复全部”；沿用当前任务 implement=inline、check=check-all-inline，不重新询问模式或范围。
- 新增真实配置保存/观察文件消费的并发回归，以及发布窗口与阈值判定的一致性回归；旧代码两项均失败，日志 /tmp/v3-warmup-race-regression-red.log 保留。
- _publish 从读取到原子替换全程持有既有 QuotaGuard RLock；warmup_snapshot 支持仅供发布复用的额度快照，避免第二次读取拼入不同窗口。
- 两项回归修复后通过：/tmp/v3-warmup-race-regression-green.log。全部 153 个后端测试通过：/tmp/v3-warmup-python-c-tests.log；Recorder 与页面未修改，既有 20 项证据仍适用。
- 新联合批次 local-warmup-20261013-c 构建通过；原 B 批次保留诊断用途，最终验收以 C 批次为准。修复后的定向验证完成，进入 Check-All 重检。
- C 批次联合构建通过。/tmp/v3-warmup-https-c-integrity.log 的 HTTPS 正文/请求数量断言通过，但最终基线保护断言失败；实际 Docker 显示无关的 new-api 容器已处于 restarting，RestartCount > 5000、RestartPolicy=always。脚本此前将 Docker 默认列表中的 restarting 也当作稳定运行基线。仅改验证脚本：明确记录并排除启动前已自动重启的容器，仍保护其余稳定容器，不操作该无关容器；原失败日志保留，复核以新日志为准。
- /tmp/v3-warmup-https-c-baseline-recheck.log exit 0：完整 HTTPS/SSE、后续拒绝、未知仅一次、重启不重复和正常作用域通过，启动前稳定运行的其它容器未启停；既有自动重启容器明确登记。
- /tmp/v3-warmup-docker-c.log exit 0：C 批次固定环境、同 run 第二代、共享 API 长流、CLI 取消/重启/Recorder 故障、双账号隔离和清理通过。
- /tmp/v3-warmup-c-source-audit.log：当前产品源码与 C 清单 SHA256 e387dababba331d11a9a7f3c89ae3b6777cce4cad680da56f824b4f64203daac 一致；原 22 项脏文件、父/子仓提交保持，cc2api 仍无修改。
- /tmp/v3-warmup-stack-browser-c.log exit 0：C 批次统一后台、HTTP/SSE/WS、实际登录/退出、阈值保存重读/独立关闭/错误输入、明暗主题/390px、离线导入幂等和备份通过，旧哨兵容器/数据库内容不变。
- 最终重检：requested=auto、effective=full、confidence=high，覆盖 27 个当前任务文件；复核发布锁、同份窗口快照、所有调用方、异常路径与旧验收映射，三维度通过，剩余 CHK/FBK 为 0。
- DOC-003：仅同步 Brief、PRD 验收状态、实施/进度和 roadmap 的已修复/本地通过事实，不改需求或设计语义。当前任务仍 in_progress，后续 Update-Spec/提交尚未执行。
