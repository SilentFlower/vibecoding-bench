# 技术设计

## 数据流

`CaptureRunIn.permission_mode` 经过 Pydantic 枚举校验后写入 `runs.capture_permission_mode`，并进入 scheduler task。`DockerRunner.start_run` 将其转换为 worker 环境变量，entrypoint 校验后向 Claude CLI 追加 `--permission-mode <value>`。

抓包 continue 从原 run 读取同一列并再次注入 worker，避免继续会话回到默认模式。普通 run 没有该字段，worker 回退 `bypassPermissions`。

## 持久化边界

新增 nullable/defaulted SQLite 列，启动时通过现有 `_ensure_column` 幂等补齐。历史 run 读取为空时解释为 `bypassPermissions`。

权限模式仅通过 CLI 参数覆盖当前进程。`write_default_settings` 和 orchestrator 的 profile 默认设置继续写 `bypassPermissions`，从而避免 run 完成后的 profile 同步把 Auto 传播到后续普通任务。

## 前端与 API

抓包表单增加两项选择：`bypassPermissions`、`auto`。请求体传递字段，详情统计区展示后端返回的快照。字段命名与后端一致，不新增页面级全局设置。

## 发布与真实验证

按项目 SOP 提交并推送 main，等待三个 bench 镜像构建成功，再以提交 SHA 镜像部署。正式抓包由 API/orchestrator 创建，完整沿用账号的 hostname、MAC、machine-id、TZ、LANG、cgroup 内存、OAuth profile、sidecar CA 和代理出口。

先通过 quota 快照选取七日额度未满且当前空闲的账号；使用自然提示词触发 Bash。只从受限原始文件生成脱敏摘要，不复制完整 HTTP 正文到仓库。

## 回滚

代码回滚为上一提交 SHA 镜像；数据库新增列可保留且旧代码忽略。远端 deployment 继续使用既有 Compose 备份与不可变 tag 回滚方式。
