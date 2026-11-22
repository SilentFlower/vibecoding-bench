# 固定版本原生研究夹具

## 边界

这些脚本用于复现私有测试环境的研究。默认离线验证入口为仓库 `deploy/flower2api/verify_agy_credentials.py`。该目录的原生脚本通过 SSH 在固定测试宿主运行，要求既有私有凭据、原版 AGY、固定镜像与研究 runtime 资源。

凭据始终保留在远端私有 HOME。生成、工具和原始 SSE 材料也留在私有目录。观察器事件含令牌摘要和原始业务块，需按私有材料处理；仓库摘要只保存代次归属、计数、字段名和逻辑块摘要。

真实模型预算已使用全部 8 次预留，当前复核使用离线方式。付费场景需独立授权和新一轮明确预算后再执行。零模型目录和异常文件脚本仍会访问 Google 账号接口。

## 文件

- `rpc_probe.py`：建立独立 AT-only HOME、校验固定原版与测试环境；脚本必须声明唯一 `MODEL_REQUEST_LIMIT`。模型预算默认 0，显式额度低于声明值时在本地退出。远端持锁校验并更新总上限 8 的私有台账后创建实验容器。
- `directory_case.py`：0 模型，GetAvailableModels 的 response 是 JSON 字符串，解码后只提取目标模型字段。
- `fault_case.py`：0 模型，用独立 `agy models` 进程测试过期、缺 expiry、坏 JSON、身份标签改变；读取账号状态仅输出字段名。
- `text_case.py`：最多 1 次生成，使用已核对的原生 RPC 和完整 hooks。
- `tool_case.py`：最多 2 次生成，通过真实回环 MCP 读取临时文件；等待期间发布另一有效 AT；核对原生 conversation、trajectory 和 toolCall 后回填。
- `observer.c` / `native_schema.h`：固定 Linux x86_64、AGY 1.5.9 的四硬件断点观察器。记录模型入口、TokenSource 读取、遥测样本和原生 Scanner SSE 逻辑块。退出事件给出实际原生 code/signal。

## 本地检查与编译

```bash
python3 -m py_compile .trellis/tasks/11-18-agy-managed-credential-contract/research/experiments/*.py
gcc -std=c11 -O2 -Wall -Wextra -Werror -DOBSERVE_ALL_STOPS=0 \
  .trellis/tasks/11-18-agy-managed-credential-contract/research/experiments/observer.c \
  -lcrypto -o /tmp/agy-credential-observer
```

当前构建使用 OpenSSL 开发头文件及 glibc。数字解析 ABI 兼容声明用于 Debian 12 测试镜像。源代码裁剪后构建产物与真实工具/SSE 实验产物 SHA256 相同：`2505f279343eb6f4d66e3dccc72cf599b91e21d7837d94a912134585e711f451`。更换编译器或依赖后需重新核对构建身份。

以下为命令结构，真实付费场景受前述预算门槛约束：

```bash
python3 research/experiments/rpc_probe.py research/experiments/directory_case.py
python3 research/experiments/rpc_probe.py research/experiments/fault_case.py
python3 research/experiments/rpc_probe.py research/experiments/text_case.py \
  --budget 1 --auth-observer /tmp/agy-credential-observer
python3 research/experiments/rpc_probe.py research/experiments/tool_case.py \
  --budget 2 --auth-observer /tmp/agy-credential-observer --swap-credentials
```

上述相对路径以当前任务目录为起点。SSH 密码由既有受限文件提供；脚本输出保持脱敏。`--swap-credentials` 从本轮最新受控刷新前快照取得仍有效的 AT1，将当前权威 AT2 放入工作副本；要求身份元数据一致、AT 不同及 AT1 剩余有效期超过 120 秒。正式账号身份验收使用已认证状态核对。

## 观察与停止

原生控制端口及 CSRF 仅在实验容器内使用。脚本退出时回收本次命名的容器。观察模式先核对 3 个遥测 client 与 1 个业务 layer，业务队列为空持续 0.5 秒后关闭输入并记录原生退出。研究 runtime 的队列读取器在 wrapper 内初始化 origins，用于本轮观察。

原生 SSE 观察点是 `codeassistclient.toStreamResponseChunk` 入口。公开摘要描述 Scanner 逻辑块。AT 读取点是 CLI auth 的 savingTokenSource.Token 调用返回处，公开报告映射到实验代次。常驻旧 AT 观察说明文件发布与进程实际采用需要分别记录。
