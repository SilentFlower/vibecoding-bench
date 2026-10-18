# 环境问题证据

- 远程默认容器 LANG/LC_ALL=en_US.UTF-8、TZ=America/Los_Angeles；但 `Runner.start_run()` 注入 derive_fingerprint(name) 的旧 locale，当前账号结果为 ja_JP.UTF-8，AccountRuntime 未覆盖。历史实际工具结果出现日文 date 与 ls 日期。
- 18 个实际项目均有系统创建的空 `.claude-home`；新 Runner 在 v3 分支前仍创建该目录，系统 session 已在固定 HOME。现有 `_session_view` 只清理可核对旧链接。
- UID1000 能读 `/usr/local/bin/v3-{account-init,network-context,cli-version,passthrough}` 与 /sidecar；源码显示它们由 root 初始化／版本安装／监听管理调用。collector 是 UID1000 本地执行入口，须维持可执行权限。
- 18 个主会话 791 次工具调用未发现明确读取管理脚本；7 个业务文件含汉字，对应多语言 demo／Unicode 测试，可追溯模型 Write。它们不属于清理对象。
- 账号列表仍从 `_effective_account_timezone` 的旧派生得到 auto 值；LoginManager.start 对 v3 默认硬编码 UTC，表单提示同样 UTC。
- `continue_run_ws.open_bridge` 另建 PTY exec，需要与 AccountRuntime 同源环境；`exec_cli`／begin_login 当前主要依赖容器默认，统一显式使用持久字段可避免入口漂移。
- /run/v3 和 /ca 已 root 私有；本任务不扩大控制目录或凭据读取权限，不重置已有身份。
- 前一个被动额度任务的代码与完整检查证据是本任务 dirty baseline，保留并复用无改动部分。生产 v3 尚未部署该功能；本任务不自动切换镜像。
