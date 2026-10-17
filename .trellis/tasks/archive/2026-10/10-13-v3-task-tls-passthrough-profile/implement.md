# 修复实施计划

## 历史

原 TLS/profile v2/工作目录隔离与未绑定阈值保存已交付：3c2a2a4；部署 ci-38404058185-1；containerd 验真修复 2652372。原画像强制重登和手动额度门禁由本轮替换。

## 本轮

- [x] 用户明确要求修复，更新同一任务方案并复用 inline 路由；保留既有用户 dirty baseline。
- [x] 额度查询使用 passthrough，不切换网络，补齐有界超时。
- [x] v3 自动采样、近期缓存、失败重试、执行前后更新和零 run 批次恢复。
- [x] 移除画像强制重登并兼容持久状态；保留真实未知提交门禁。
- [x] 未绑定养号的配置、触发、结束、恢复和定时扫描。
- [x] 具体等待原因与维护提示、全局运行配置回归。
- [x] 幂等 up 和可配置资源余量，外部资源隔离回归。
- [x] 定向/全量测试、静态检查、隔离 Docker 与浏览器，Check-All。
  - 后端 232、部署 32、账号镜像 8、sidecar 20 项通过；新增自动采样 11 项包含锁重入与全局配置。
  - /tmp/v3-repair-checked-tests.log、/tmp/v3-auto-usage-final.log、/tmp/v3-runtime-final-tests.log。
  - /tmp/v3-quota-auto-docker.log：真实 TLS usage JSON、原生监听 PID 保持、API 长流与 CLI 隔离。
  - /tmp/v3-quota-auto-browser.log：统一 stack、表单 API、明暗/390px、退出和旧服务哨兵。
  - profile_reauth_reconcile 兼容故障返回已定向复核；最后表单绑定提示通过 JS 语法与数据流审查。
- [x] 同步规范并推送已确认范围，ci-38423283134-1 构建、GHCR 发布、镜像交付与停机备份完成。
- [x] 美国服务器 v3 启动；用户要求跳过部署预检并保留原密码，改用直接 Compose 启动。旧 bench 8080 / cc2api 5674 的容器 ID、镜像和启动时间保持。
- [x] 生产发现 GET usage 的空闲 0% 可带过去/null reset；补充修复和三项回归，235 项后端测试通过，语法与 diff 检查通过。
- [x] 应用调度热修复后，10-13 原画像与 HOME 保持，state=ready；真实自动额度为 5h/7d 0%，原 600 题批次自动恢复，19c3df0244bc 普通任务以 passthrough、2.1.293/xhigh/opus[1m] 启动。
- [x] 首条任务实际停在目录信任页，恢复原题投递并观察到真实 assistant/Bash 工具调用；新项目准备时自动保存当前专属 cwd 的信任标记，身份与其他项目不变。46 项定向及 235 项全量回归通过；全量首次出现一次零 run 批次断言失败，定向和带脱敏诊断的全量重跑均通过，诊断日志保留。
- [x] 用户指出 19c3df0244bc 重复报错：真实 transcript 证明内部 Stop hook 无权写 runtime/jobs，CLI 多次给出完成回复仍反馈 hook 错误，最终 timeout。移除没有消费者的 v3 时间戳 hook，原 run 的真实 timeout 记录保留。236 项全量回归及实际生成 driver 的设置/无 Stop 信号完成判定通过；零 run 场景连续 20 次通过。
- [x] 本次备份的真实故障为残留 tmux Unix socket：源文件保留，快照排除 socket；32 项部署回归覆盖真实 socket、WAL、普通文件和符号链接。
- [x] 用户要求关闭自动更新：官方 DISABLE_AUTOUPDATER=1 已在当前 v3 HOME 设置生效，CLI 统一准备入口补齐持久规则；237 项后端回归通过。
- [x] 实测 10-13 UID1000 的 HTTPS 出口与抓包 proxychains 出口均为 216.36.119.5；真实配置为 HTTP us-8.flower-cli.com:38888，容器内部入口为 SOCKS5。当前默认路由 tun0，抓包配置沿同一 HTTP 上游。
- [x] 同类审查确认重启后 active 批次缺调度线程：v3 启动重新注册原批次，保留已保存的间隔和 item 状态，暂停/删除/停用账号不恢复；已结束 run 不重写。
- [x] 全部修复已纳入正式镜像 ci-38442193885-1，GHCR 发布与交付包 SHA256 校验通过；停机备份 /opt/vibebench-v3-us/backups/pre-ci-38442193885-1，直接 Compose 启动保留原密码，账号经公开维护入口重建到同批镜像。
- [x] 最终生产回读：管理服务 running/gateway healthy，旧 8080/5674 容器 ID、镜像及启动时间不变；10-13 画像等于发布前，HOME/凭据保留，generation=4/state=ready，passthrough ACK匹配。
- [x] 真实自动额度 5h 已用 10%、7d 已用 2%；原 85% 阈值保持，批次恢复 active 并自动投放 761ca2598a04。新题无中文内容，CLI 2.1.293 / xhigh / opus[1m]；真实 assistant 与工具调用，未观察到 API、Stop hook 或自动更新权限错误。此记录不把仍运行的新任务冒称 success，旧 19c3df0244bc 的 timeout 保留。
- [x] 最后回归：238 项后端、32 项部署，实际生成 driver 的无 hook 完成判定、零 run 连续 20 次、语法及 diff 检查通过。生产验收证据 /opt/vibebench-v3-us/operations/upgrade-ci-38442193885-1/deployment.json。
- [x] 任务记录确认范围核验完成；完成态与 Close 由 task_progress.py 在任务记录提交前原子写入，随后按原确认范围推送。
