# 登录草稿与终端取证

- 父仓 v3 已发布并部署 ci-38336364164-1；此任务创建前两仓业务与上次任务记录已提交。当前基线保留二十二份旧无关变更。
- 仅只读获取 v3 环境记录、当前 tmux 输出的 URL 结构与状态；不取消/提交实际登录，不保存 URL、state、code_challenge 或凭据。
- 当前草稿 10-13 的环境 ID 为 5d9157a2091d48d9be8989697dc673a2，环境账号 ID 尚未关联正式账号，容器存在。名称仅用于取证，不作为允许直接清理该真实草稿的授权。
- 新会话 capture-pane 带目标与不带目标都成功，输出 576 字符。候选主机 claude.com、路径 /cai/oauth/authorize，state/challenge 均为 43 字符 base64url；当前解析器只接受旧主机与 /oauth/authorize，返回 None。
- 旧截图会话终端随后不存在，状态 API 返回 404。不能复原原屏幕或未经验证宣称首张截图与新会话只有一个共同根因。
- 已阅读 frontend/hook-guidelines 及 backend/account-runtime-v3 的相关场景；新任务保持 planning，未写产品代码。

## 产品决定与宕机恢复问题

- 用户选择“全部清理未提交草稿”：未来列表删除入口应清理草稿、专属容器和未提交目录。该决定授权本任务设计，不授权立即删除当前真实登录草稿。
- 用户询问服务器宕机后是否自动启动账号容器：当前两个管理服务 restart=unless-stopped，账号创建未配置 restart_policy；后续 transport/CLI ensure 负责按需唤醒。管理启动先 reconcile 遗留执行，再启动心跳与调度；不能承诺恢复宕机前的 tmux/WS 交互进程。
- 服务器官方 CLI 缓存为 2.1.293；其 native 可执行文件内明确包含 https://claude.com/cai/oauth/authorize 与 https://platform.claude.com/oauth/authorize。实际当前链接被旧白名单拒绝，问题已由真实 CLI 输出和二进制常量双向确认。
