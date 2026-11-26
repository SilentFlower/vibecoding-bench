# V2 交互 CLI 原生发送的本机候选

在一次性的 Linux 账号容器中运行真实网关、账号发送器和固定 2.1.293 CLI。公开入口为 `POST /v1/messages`。合成 HTTPS 模型与原会话的本机回调共用获准端口。测试使用临时 CA 和合成账号，查看对端套接字是否属于该 CLI 的 PID，再比较接收正文与已认领正文的摘要、大小和有序头名。输出中保留事件计数与摘要。

## 从源码复跑

准备能在所选账号基础镜像中运行的同一源码网关和发送器，以及现有的固定版本 CLI 安装目录。将命令中的两处宿主机路径换成实际绝对路径。账号数据卷使用容器的临时文件系统。

```bash
docker build --network none -f deploy/flower2api/fixtures/native_model_send/Dockerfile \
  --build-arg ACCOUNT_IMAGE=ghcr.io/silentflower/flower2api-account:v3-ci-45743360178-1 \
  -t flower2api-account:native-model-test .
docker run --rm --init --network none \
  --mount type=bind,src=/path/to/compatible-gateway-binaries,dst=/verify-native/bin,readonly \
  --mount type=bind,src=/path/to/cli-installations,dst=/cli,readonly \
  flower2api-account:native-model-test
```

二进制目录包含 `claude-code-gateway` 和 `account-sender`。CLI 安装树使用账号镜像的现有 `/cli/2.1.293` 布局。测试创建空白 SQLite 库，经管理接口绑定合成账号和 V2，在本机 TLS 模型上跑工具首轮及 JSON 续轮。

## 观测口径

- 首轮参数只送到一半时，客户端先检查文件访问记录，暂停读取，再让模型发送后半段。最终文件访问次数来自 Linux inotify。
- 在真实模型投递前，内层 CLI 重放同一步骤，账号端应拒绝第二次认领。上游发送、完整账本和客户端文件读取独立计数。
- 使用新会话在半截工具参数处关闭客户端。模型端应观察到连接或步骤结束，本轮工具不执行。
- 模型端核对校验过的正文与身份。它接收 CLI 发出的真实 TLS。计费断言使用公开网关的合成用量记录，客户端返回通道也核对完整事件摘要。
- 同一会话尝试外部 CONNECT 时，现有回调继续拒绝。正式供应商的代理出口、供应商额度响应头、签名修复、原生 TLS 写出诊断，以及断线后的重领和恢复需要另外联测。实验接收端的记录保留其本机观测来源。

## 验证账号代理

仍使用上面的两个只读挂载和 `--network none`。在 `docker run` 的镜像名前加 `--entrypoint python3`，镜像名后传入以下参数：

```text
/verify-native/verify_proxy.py --gateway /verify-native/bin/claude-code-gateway --sender /verify-native/bin/account-sender
```

代理只接通 `model-probe.invalid:443` 到同容器内的合成 HTTPS 模型。正对照通过同一代理使用固定版官方 CLI，再用普通 HTTPS 客户端在一条 TLS 连接上提交两份不同正文。受管对照从已认领模型步骤的交互 CLI 尝试会话代理与账号配置的代理。分别核对代理的 TCP 接入次数、CONNECT 次数、HTTPS 模型实际收包次数，以及会话回调观察到的进程号和状态。原有工具两轮和取消继续通过本地模型作独立对照。

## 验证受管主请求与标题一起经过账号代理

使用相同的源码构建与只读挂载，将脚本改为 `/verify-native/verify_managed_proxy.py`。脚本无参数开关时运行原生自动命名对照组。在新容器中加入 `--fixed-name` 验证受管启动器使用完整的预留会话 ID 命名。每个容器只使用合成凭据。

公开 Messages 先进入真实网关和账号服务。交互 CLI 只连接其专属会话端口，这个测试入口核对套接字属主和当前合成账号，然后经账号配置的独立 HTTP 代理接到固定域名的独立 TLS 模型。三个监听器使用不同的回环端口。主轮核对已认领正文与实收正文的字节摘要。自动标题由仓库的原生分类器识别，原始回复只交回 CLI。账号侧单独记录从标题回复读取的用量，主轮仍读网关 SQLite 账本，再逐项与模型侧响应交叉核对。进程退出后清点整场请求。
