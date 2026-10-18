# 实施计划

## 顺序

1. [x] 评审 Brief 并启动；进入 implement route，读取 before-dev 及相关实际类／DTO；保留创建任务时记录的 dirty baseline。
2. [x] 统一 v3 默认时区与持久环境读取；覆盖 start_run、设置、登录／短命令／续聊入口以及页面有效时区，不改变旧 runner。
3. [x] 阻止 v3 创建 `.claude-home`，补安全空目录清理与非空／链接保护。
4. [x] 调整账号镜像管理脚本和 /sidecar 权限；保留本地额度采集可执行。
5. [x] 运行定向及完整相关验证，联合构建并隔离 Docker／浏览器验收；完成 Check-All。

## 预期范围

- `orchestrator/account_runtime.py`、`main.py`、对应环境／Runner／登录测试。
- `images/v3/Dockerfile`、`webui/index.html` 的默认提示，必要的有效时区展示。
- `deploy/v3/verify_local.py`、`fixtures/mock_cli.py` 的实际环境／权限／目录断言；如需要，扩展页面场景。
- 本任务记录及相应 runtime 规范；不回滚上一个被动额度任务或用户既有 spec／两个 10-12 任务内容，不改 cc2api 行为。

## 验证

- 纯逻辑：默认 LA／en_US；显式 UTC／Tokyo；旧持久字段；错 worker_env 与 settings.env 覆盖；页面读取不创建环境。
- 文件边界：实际 Runner → AccountRuntime 产生的项目无 `.claude-home`；空目录清理、非空保留、链接保护、session 恢复。
- `python -m unittest discover -s orchestrator -p 'test_*.py'`，相关部署与账号网络单测；Python 编译、生成 driver bash -n、JS／diff 检查。
- 联合镜像 build、`run_local_verification.py`、`verify_stack.py --browser`：实际 UID1000 locale／ls/date、运行 env 记录，root 管理脚本不可读而 collector 可执行，网络／抓包／登录／恢复／API 长流保持。
- 使用本地合成凭据／上游，不请求封禁账号。未变的 cc2api Rust 证据可复用上任务结果，只有相关源码变化才补跑。

## 回退与交付

无数据库迁移；镜像切换按现有联合版本流程，保留 HOME／会话／凭据。不得把隔离验证等同于生产账号恢复或保证不被限制。

## 用户追加事项

6. [x] 逐项替换题库排除主题，同步分类风格与校验；检查 600 题、英文／编号／分类一致及同步历史不变回归。数据库同步留给后续部署。

## 验证记录

- 当前范围 Full Check-All：三件套实现、实现假设、完整性与规范均通过；CHK=0、FBK=0。规划允许的新默认／主题契约在后续 Update-Spec 同步，尚未 Git 交付或部署。
- 后端完整回归 251 通过：`/tmp/v3-environment-orchestrator-passed.log`；部署单测 32 通过：`/tmp/v3-environment-deploy-tests.log`；账号网络单测 8 通过：`/tmp/v3-environment-network-tests.log`。
- `scripts/sync-topics-db.py --validate-only` 通过；600 题两套解析器逐字段一致，21 分类均命中风格，1200 条自然／规范提示无 CJK 或全角标点；历史 topic ID／prompt 回归包含在后端测试。
- Python 编译、JS 语法、生成 driver Bash 语法（真实 Runner 测试内）及 git diff --check 通过。
- 联合镜像清单：`/tmp/v3-environment-release-r1.json`，release=`v3-local-20261014-environment-r1`、linux/amd64、dirty=true，冻结输入 SHA256=`01408810b0e698ae90aa4cae05b3a994e43596a781c71b5ac31fc2f993b9bf36`；重算当前输入一致。构建输出：`/tmp/v3-environment-build-r1.log`。
- 隔离 Docker 生命周期通过：`/tmp/v3-environment-docker.log`；实际合成 CLI 的 TZ/LANG/LC_ALL、locale、英文 date/ls、管理脚本不可读、collector 可执行、原生 TLS／capture／重建／API 长流均通过。
- `verify_stack.py --browser --reauth` 通过：`/tmp/v3-environment-stack.log`；真实 Chrome／HTTP／WS／tmux／双数据库的草稿与重授权、取消、重启恢复、凭据保留和专属删除，旧哨兵不变。CLI 和 OAuth 为测试替身，无真实封禁账号请求。
- 页面定向验收：`/tmp/v3-environment-browser.log`，1280／390 明暗主题、洛杉矶默认提示、已固化 UTC 展示、原被动额度逻辑与单次手动 POST。
- 复用上任务 cc2api 639 个 Rust 通过、1 个 PostgreSQL 测试未配置 DSN：`/tmp/v3-passive-cargo-all.log`；与任务创建 baseline 的子仓 diff 哈希完全相同。34 个既有未跟踪文件哈希保持，用户 protocol-capture spec 既有 45 增／1 删保持。
- 初始后端回归曾因测试夹具缺少 app_settings／fingerprint_json 和新分类风格未同步失败，修复后完整 251 项通过；首次 Docker 命令在清单生成前失败，联合构建完成后同清单验证通过。
- 上线后由部署负责人切换已核对的联合镜像，显式同步并备份线上 topics；再用可用测试账号验证正式 CLI 环境与已有 HOME／会话保留。已有画像、历史任务 prompt 及封禁原因不作自动改写或推断。
