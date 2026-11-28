# V2 原生发送验收夹具

本目录的现行模块供 `deploy/flower2api/verify_tui_cold_history.py` 使用。

旧本机候选的独立镜像、替换事件源和预加载模块保存在提交 `4e8340f4c00c5969ea0f30b57533582926e55c59`。从该提交的冻结检出按同路径 README 复跑，使用该提交的网关与账号发送器、固定 CLI 2.1.293、一次性账号目录及 Docker `--network none`。

R4 标题回归的合成入口样本可用 `ce2c90ff` 中的 `verify_managed_proxy.py --export-title-request` 重新生成。它使用旧候选所在的隔离镜像，其余公开标题验收从现行入口运行。
