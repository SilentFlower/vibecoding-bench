# 输入与草稿恢复证据

## 已确认事实

1. 真实 CLI 2.1.293 隐藏授权码回显。2026-10-13 以真实 native 二进制、临时 Docker、全新 HOME、禁网运行 `claude auth login`，TTY 模式包含 `-echo -icanon -isig`；两条 PTY/tmux 输入路径均不显示测试文本。输入合成无效码并 Enter 后出现 `Invalid code. Please make sure the full code was copied.`。证明 CLI 收到该次测试输入，不证明用户浏览器全部输入送达，也没有完成真实 OAuth。
2. 终端内边距点击存在焦点缺口。隔离真实 Chrome 点击 host 边框/内边距时 activeElement 为 BODY，内部屏幕为 xterm textarea；已有补丁将 host 点击焦点交给终端。验证脚本已使用真实键盘输入替代直接 WebSocket 注入。
3. 用户真实草稿曾因取消清理的 `_configure_recorder` 失败进入 reconcile；当时容器 exited、无作业，保留执行证明，草稿与原代次可核对。用现有维护 API 对账一次后旧执行证明删除、状态恢复 cancelled、HOME 身份摘要不变。用户此后自行删除/重建，旧环境 ID 不可用于再次操作。
4. 生产错误是网络上下文切换失败；未证明是旧进程退出、新进程启动或具体超时哪一项导致，不能把候选机制写成根因。
5. 已查到草稿代理配置仍存在；页面 `<td colspan="4">` 合并代理列。此为展示缺口，不是代理被删除。
6. 旧 cc2api 的唯一 API 令牌已按用户请求复制到 v3，数据库全字段一致，并在不调用真实上游的空正文请求中证明鉴权生效。本任务不重复迁移或记录令牌值。

## 规划时的代码锚点（实施前工作区）

- `webui/app.js:229`：草稿行合并代理等列。
- `webui/app.js:770`：登录终端 attach；`webui/index.html:518`：登录 modal。
- `orchestrator/main.py:4533`：LoginSession 定义；`:5061`：对账后会话清理；`:8425`：现有 login WS 输入/输出桥。
- `orchestrator/account_runtime.py:807`：登录/CLI 清理；`:967`：原 tmux 登录创建；`:1206`：维护入口。
- `cc2api/src/service/runtime_bridge.rs:152`：浏览器 `/accounts/` 路径桥接白名单。

## 证据与实施边界

- 本地禁网实验记录在 `/tmp/v3-native-input-probe.py`、`/tmp/v3-native-input-probe-confirm.py`；252755128 字节真实二进制仅在临时实验目录，不进入仓库。
- 生产热补丁备份和核对记录保存在服务器 `operations/terminal-focus-hotfix-20261013/` 与 `operations/terminal-input-hint-20261013/`；只修改前端容器文件，未持久固化镜像。
- synthetic CLI 的成功回显不能代表真实 CLI；新验证必须分开记录 native 校验实验和合成全流程结果。
- 任务规划阶段没有操作真实登录；本轮实现与验证同样仅使用隔离数据，不承诺真实 OAuth/Recorder 底层修复已完成。


## 本轮实现验证证据

- 后端：在 `orchestrator/` 中用 `/tmp/v3-verify-venv/bin/python -m unittest test_login_reauth test_login_drafts test_account_runtime`，67 项通过（26.781 秒）。ASGI 客户端依赖来自 `orchestrator/requirements-test.txt`，不增加产品运行依赖。
- 真实 CLI：`/tmp/v3-code-native-20261013.py` 使用本轮 `AccountRuntime.send_login_code`，验证同一原 tmux 收到合成无效码、临时 buffer 清除、Docker network=none；退出 0。该实验没有完成真实 OAuth。
- 最终双镜像清单：`/tmp/v3-code-feedback-d.json`，批次 `local-code-feedback-20261013-d`；冻结源码 SHA256 为 `00f819f775be32f3feb77f5cbf439aedde44a7e632698f62c60a5a68b57f391e`，两个镜像 ID/批次与当前源码匹配。
- 隔离 Docker：`run_local_verification.py --manifest /tmp/v3-code-feedback-c.json` 退出 0，日志 `/tmp/v3-code-feedback-local-c.log`；API/CLI 并行、原 HOME/容器、网络故障与续聊清理回归通过。
- 真实 Chrome/HTTP/WS/tmux/双 DB：`verify_stack.py --manifest /tmp/v3-code-feedback-d.json --browser --reauth` 退出 0，日志 `/tmp/v3-code-feedback-stack-d.log`。覆盖真实键盘、原生 Ctrl+V、显示切换/长度、按钮/Enter、回包丢失查询、单次投递、WS 断线独立发送、明暗/1280及390布局、关联凭据保留、宕机恢复、清理故障恢复和完整删除；另覆盖 Terminal/FitAddon 缺失时重连禁用、独立投递与取消；旧测试哨兵及数据库不变。
- 原生右键系统菜单未由 CDP 自动驱动；页面使用原生输入框且不拦截 contextmenu/paste，已验证对应的原生粘贴输入路径。真实用户浏览器的系统菜单与真实 OAuth 全流程留作上线后操作验证，不能声称已完成。
- 本轮无远程部署、真实账号取消/删除或旧服务操作。22 项无关 baseline 内容摘要未变化，cc2api 仍 clean，HEAD 为 `4f1ed1f208cdf831c56d03026e249a758b248fa7`。

- 最终重检：后端与单测文件摘要同 C 批次，67 项单测、真实 native 与本地 Docker 证据复用；D 批次只修正输出组件不可用时的重连许可，并重跑完整 Chrome/HTTP/WS/tmux/双 DB 流程、JS/验证脚本语法与冻结双镜像校验，全部通过。规范同步到输入回执与恢复契约，未修改无关捕获规范。
