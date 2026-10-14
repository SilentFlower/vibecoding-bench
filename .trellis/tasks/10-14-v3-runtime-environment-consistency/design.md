# v3 执行环境一致性设计

## 权威来源与默认

复用 `account_environments.fingerprint_json` 的 `tz/lang`，不新增表或用户配置项。默认常量为 `America/Los_Angeles`，供 `derive_v3_fingerprint`、新登录与未初始化页面摘要复用；locale 继续通过现有 `locale_for_timezone`。已有 fingerprint 保持原样，容器 ensure／重建与任务执行都读取同一记录。

## CLI 入口

在 AccountRuntime 统一提取 `{TZ, LANG, LC_ALL}`，按已保存字段生成。`start_run` 在上层 worker_env 合并后覆盖这三项；`_cli_setup` 将相同键合并进固定 HOME settings.env，保持其他 env／设置。登录与短 CLI 命令、续聊 PTY 入口显式使用同一来源；暂存重授权 HOME 沿用原账号设置。网络代理、TLS、CLI 版本、权限模式与额度逻辑不改。

页面 `effective_timezone` 读取已有环境行；不存在时只计算新默认或显式配置，不创建账号容器／环境。旧 runner 仍使用旧派生与 HOME。

## 项目目录

Runner 只在旧 runner 分支创建 `.claude-home`。v3 `_session_view` 延续已知旧 session 链接清理，并为当前专属项目的非链接空 `.claude-home` 使用 rmdir；非空或未知链接保持，不递归删除。项目别名、兼容链接及主会话实际 HOME 保持。

## 运行文件权限

账号镜像里 `v3-account-init`、`v3-network-context`、`v3-cli-version`、`v3-passthrough` 由 root 使用，设为 0700；/sidecar 根目录 root 0700，内部文件不需要逐个删注释。`v3-cli-quota` 保持 0755；正式 CLI 不读取或执行管理脚本。以 Docker 内 root 初始化／抓包和 UID1000 Read／执行测试确认此边界。

## 兼容和回退

已有环境、用户显式时区及未知设置保留；变更仅校正每次执行从错误旧值到既有权威值。默认只影响新环境，不自动迁移历史 UTC 环境。清理仅空系统目录，无用户内容删除。镜像回退会重新引入旧执行 locale 与目录问题，已有 fingerprint／HOME／session 保留；生产切换前仍按现有联合镜像 SOP 处理。

## 题库追加设计

用户已明确替换主题边界，追加本地 topics.md、分类风格映射和同步校验规则。逐题语义筛查，不把普通文件 scan、游戏 health 或课程 training 误当排除领域；保留标题／描述英文、题号及总数。将安全分类更名为 Organization and Recordkeeping Tools，并让新分类使用产品风格。同步校验按具体词组及领域表达拒绝模型训练／微调、网络协议／代理／扫描／安全、生物医疗题目，避免泛关键词误报。测试覆盖拒绝与保留两组。线上数据库和已创建任务不自动回填。
