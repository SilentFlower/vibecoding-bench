# Claude Code 2.1.293 请求内核

原生 V1（`request_backend=native293`）使用 Claude Code 2.1.293。交互式 V2（`tui_v2`）也使用 2.1.293，通过账号环境安装的官方 CLI 启动。客户端版本准入由网关的访问设置管理。请求记录仍展示该次请求实际使用的版本。

## V1 制品与安装

| 对象 | 字节数 | SHA-256 |
| --- | ---: | --- |
| 官方 Linux x64 源文件 | 252755128 | `8968405e26db478af44eabc4635ab5ca557057b702a54460a59c13e1b253e978` |
| 账号镜像中的 `/usr/local/bin/ccrb-runtime` | 27392144 | `017ec892b9dfbf08bf4cb2e5bf59048cb41a0ecfc21b1ad518751a23a911b9b7` |
| 执行映像 | 112852152 | `eec33dc1466f4180f0448b2524c67b10656764603592aad73e26b0389d3c26eb` |

CI 从固定 npm 归档核验 SHA-512、官方文件 SHA-256、构建报告、当前源码输入和最终分发摘要。缓存命中时继续校验。Linux x64 本地构建需要 Bun、GCC 和建立隔离网络命名空间的权限。

```bash
python3 services/runtime/scripts/prepare-ci-runtime.py --source-version 2.1.293 --directory /绝对路径/native293
export V3_NATIVE_RUNTIME_ASSET=/绝对路径/native293/ccrb-runtime
```

## 升级与运行

账号镜像声明 `vibebench.native-runtime-versions=2.1.293`。从旧双版本环境升级后，编排端从安装信息中选用 293，网关按 293 准备和派发请求。旧版请求详情保留其采集时的版本。

私有执行请求显式指定 `source_version=2.1.280` 时，sender 在启动进程前返回 HTTP 400。公共 `/v1/messages` 上的普通 API 请求按现有准入规则处理。带版本标记的原生正文仍须符合 293 的输入合同。

同一账号共享只读执行映像，每个 worker 有独立的堆、SDK 和请求缓冲。额外暖进程按 `native_idle_timeout_secs` 回收，默认 120 秒。安装信息、准备状态、进程数及制品摘要可在环境的「请求内核」面板核对。
