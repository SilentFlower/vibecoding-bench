# 构建与兼容演练性能研究

## 本项目证据

- 基线见 `performance-baseline.json`：v1.1.1 的构建327秒，兼容演练448秒，基础合同回归39秒。
- `deploy/v3/manage.py:444`：两个角色按同一暂存快照构建；原入口使用普通 Docker build，随后读取实际本机镜像生成联合清单。
- `images/v3/Dockerfile:26`：Cargo registry、git、target 是三个具名缓存挂载；构建出的交付二进制复制至普通镜像层 `/out`。
- 两个 v3 workflow 使用独立的 GitHub 托管 runner。2026-11-12 的 Actions cache usage 查询为0项、0字节。
- `deploy/v3/verify_database_compatibility.py:194`：已验签的最近8个来源串行执行，每个来源独立临时目录、双库和 UUID；容器网络为 none，内存上限768MiB，网关端口仅位于各自容器内。
- `deploy/v3/test_system_workflow.py`：自动构建要求 contents:read、零发布步骤；手动发布要求来源/签名预检和真实兼容验收先于推送。

## 外部机制与选型

1. Docker 外部层缓存与 RUN 缓存挂载分别保存。GHA 层缓存使用 API v2、按角色分 scope；Cargo挂载另外通过 Actions cache 与挂载导入/导出保存。
2. 普通 shell 调用 Buildx 需要显式接入 GitHub runtime 环境；采用已发布的 helper，保持发布私钥仅在原有签名步骤提供。
3. 使用支持 builder 和具名 mount id 的 cache-dance v3.4.0；Docker 文档中旧 v2 示例的接口不足以表达当前三个自定义 mount id。
4. 两个 workflow 复用本仓 composite action，集中缓存准备、builder、恢复/保存策略；现有 build 命令与冻结批次继续共用。
5. 同一流水线的缓存和演练并发共同验收，作为一个性能交付项收口。

已核对的固定版本：

| 组件 | 固定提交 | 已核对接口 |
| --- | --- | --- |
| crazy-max/ghaction-github-runtime v4.0.0 | 04d248b84655b509d8c44dc1d6f990c879747487 | GitHub runtime 环境；Node24 |
| reproducible-containers/buildkit-cache-dance v3.4.0 | 5422eac04292c961a382e0f584ea0f03ad9da723 | cache-map、builder、skip-extraction；Node24 |

## 权威来源

- [Docker：GitHub Actions 缓存](https://docs.docker.com/build/ci/github-actions/cache/)
- [Docker：GHA backend、作用域及 shell 鉴权](https://docs.docker.com/build/cache/backends/gha/)
- [cache-dance v3.4.0 接口](https://github.com/reproducible-containers/buildkit-cache-dance/blob/5422eac04292c961a382e0f584ea0f03ad9da723/action.yml)
- [cache-map mount 参数](https://github.com/reproducible-containers/buildkit-cache-dance#cachemap-options)
- [runtime helper v4.0.0 接口](https://github.com/crazy-max/ghaction-github-runtime/blob/04d248b84655b509d8c44dc1d6f990c879747487/action.yml)

## 验证判断

- 日常构建采用缓存，不把普通构建生成的历史发行作为当前正式批次直接晋级。
- 用全新 builder 和相同输入比较冷/热构建，记录恢复、构建及保存步骤，避免只比较编译片段。
- 兼容演练保持相同8个来源，先串行再两路并发，核对结果等价、隔离、失败传播和资源收口。
- GitHub cache 的真实跨 runner 命中在代码推送后以正常构建及同 SHA 再次手动构建核验。本地验证与远端实测分别记录。

## 实测收口（2026-11-12）

- 业务来源：73d7f871725194a6b9a7a730992ab0c2bde267d0。两个GitHub托管runner分别为1000007108、1000007109，两轮清单均为干净来源。源码内容摘要同为537d0d747f15f63b943749da5ea44c7bfb3f457c2d21d67c33a01db2e2f8e32c。
- 首次自动构建：[43223707456](https://github.com/SilentFlower/vibecoding-bench/actions/runs/43223707456)。缓存未命中，镜像构建548秒、准备9秒、保存93秒，缓存相关构建合计650秒；完整job735秒。
- 同SHA手动构建：[43225824340](https://github.com/SilentFlower/vibecoding-bench/actions/runs/43225824340)。Cargo主键精确恢复，Rust构建层命中，缓存顶点由16增至94。镜像构建186秒、准备32秒、post4秒，合计222秒；完整job301秒。
- 与旧327秒构建基线相比，计入缓存开销的热构建缩短32.11%。首次初始化缓存成本较高。两轮同输入缓存相关耗时缩短65.85%，完整job缩短59.05%。首轮成本与热构建收益分别保留。
- 本地八条合成历史使用四个真实历史镜像，串行289.825秒、双路147.460秒，两份证据完全相同；迁移启动故障注入后19个本次容器全部收口，成功证据保持空缺。正式最近八个发行的双路演练由下一次明确发行验收。
- 本机已有builder的两轮实际联合构建为229.756／100.831秒，按现有inspect_images入口核对身份、来源和镜像内flower2api前端。此结果按已有缓存条件记录。

复测入口为同一业务SHA的v3-build自动构建完成后，执行gh workflow run v3-build.yml --ref flower2api，并核对实际解析SHA、恢复主键、Rust缓存层、两镜像清单及cache准备/保存与完整job耗时。双库对照使用同一候选清单与合成签名历史，分别调用verify_database_compatibility.py --workers 1和--workers 2，再比较完整证据。原始运行和逐步骤数据见performance-results.json。
