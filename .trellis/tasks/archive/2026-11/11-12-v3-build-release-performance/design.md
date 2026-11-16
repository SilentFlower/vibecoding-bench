# v3 构建与发布性能设计

## 范围与实施位置

在 `flower2api` 分支优化同一 v3 流水线的两个主要耗时段。项目源码、业务数据库、账号生命周期及正式发行格式沿原合同；缓存和并发均作为可关闭的性能机制。缓存与演练统一按同一候选输入、来源及验证要求收口。

## 构建缓存

### 共享接线

新增 `.github/actions/flower2api-build-cache/action.yml`，由 v3-build 和 v3-release 共用。采用官方 Buildx setup、Actions cache，以及 research 中固定提交的 runtime helper 和 cache-dance。缓存准备位于现有 build 步骤之前；Cargo挂载提取、缓存保存及 builder 回收依照明确的 post 顺序完成。

缓存材料放在 runner 临时目录，源码快照继续由原白名单生成。构建日志只记录缓存状态、作用域及耗时，凭据不进入命令参数、镜像或缓存目录。

### 分层策略

- Docker层：使用 GHA API v2、mode=max；平台和缓存格式版本组成命名空间，control/account 各有 scope。
- Cargo挂载：保持 Dockerfile 现有三个 target 和 id；用 cache-map 对应 registry/git/target。缓存键包含平台、Rust/Dockerfile/依赖配方及源码输入指纹，恢复前缀限兼容配方，避免纯任务记录提交反复保存相同源码缓存。
- 可信写入：正常目标分支的 push 与手动构建可保存缓存；PR采用受 GitHub 分支隔离约束的读取策略。自动构建的 contents:read、checkout凭据关闭和零产品发布副作用保持。
- 缓存属于加速层，首次、未命中及服务不可用时执行完整构建。缓存恢复/保存失败单独报告；构建、迁移及发布错误原样阻断。

### 本地入口与可选构建模式

保留 `manage.build(release, manifest_path)` 的现有调用方式。拟通过可选环境接线命名 Buildx builder 和 GHA缓存 scope；未启用时沿用普通 Docker build。缓存模式执行 `docker buildx build --load`，仍以实际加载的镜像身份生成联合清单。所有来源标签、run/attempt/SHA、source_content_sha256及配置摘要按原逻辑核验。

拟新增环境合同由实现阶段对应单测与规范明确：`FLOWER2API_BUILDX_BUILDER`、`FLOWER2API_BUILD_CACHE_SCOPE`、`FLOWER2API_BUILD_CACHE_WRITE`。builder和scope只接受受限名称；GHA鉴权来自runtime环境，未具备缓存上下文时明确转入无外部缓存路径。

## 兼容演练有限并发

拟扩展 `verify(..., *, history_root=None, workers=1)` 和 CLI `--workers {1,2}`；默认1保留原调用行为，发布workflow显式使用2。

1. 在协调线程读取并验签来源集合，核对候选镜像与冻结双库登记。
2. 把原 for 循环中的单来源验证提取为一个职责完整的 worker。每个 worker 保持原 UUID、临时根、双库快照、实际镜像摘要和容器安全参数。
3. 最大同时执行两个来源，覆盖原升级、两次迁移、候选读写、原版读写和快照恢复，继续使用原健康/停止/命令期限。
4. 协调线程按完成事件收集结果，按原来源序号归位。全部成功后才原子写入成功证据，原证据字段与验证器保持兼容。
5. 首次失败后取消待运行任务，等待已开始任务执行 finally 收口，再携带来源身份传播原异常。成功结果不得遮蔽任一失败。

每个来源的耗时及总体耗时通过独立性能日志记录；正式兼容证据保持现有schema。无真实模型请求，Docker操作限定本次隔离容器与临时目录。

## 影响文件

- `.github/actions/flower2api-build-cache/action.yml`，两个 v3 workflow。
- `deploy/v3/manage.py`，`verify_database_compatibility.py`，相关工作流、构建与兼容回归。
- `deploy/v3/README.md`、`SYSTEM-UPDATES.md` 与平台部署权威规范。
- 当前任务的来源、基线及性能验证记录。

固定宿主源码包继续采用原路径和依赖边界；若引入 manage 的直接依赖，必须同步固定包清单与仓库外独立导入测试。首选保持标准库与现有模块依赖。

## 验收与恢复

- 验收同时比较冷/热缓存和串行/双路并发，报告实际输入、镜像身份、覆盖来源、运行环境与步骤耗时，验证真实收益及传输开销。
- 含真实Docker的本地隔离回归先覆盖功能等价、失败与收口；GitHub 跨runner缓存命中在业务推送后核对自动构建和同SHA再次手动构建。
- 关闭缓存接线可恢复原 Docker build；`--workers 1` 恢复串行。上述恢复保持原批次与数据合同。
- 本任务交付不直接触发正式发布，正式发行和生产安装按后续明确动作执行。

## 增量：flower2api 展示名称与README

用户已明确展示名称使用小写 flower2api；页面、CI和第一方文档统一收口。新建缓存action及其新环境项采用flower2api命名。既有内部镜像、环境变量、部署路径、API字段、浏览器存储键和签名通道继续保持兼容。

- Vue浏览器标题、登录与管理标题、调度说明及静态工程页的品牌文案统一。
- 根README以统一产品、源码目录和实际构建发布/升级入口为主。旧版部署细节通过明确的历史说明入口保留。
- 网关README改为本仓组件指南，旧说明按历史参考保留，来源与许可继续可追溯。运行时README调整产品入口，保留实际CLI及协议标识。
- 编排器新增README，按当前入口、账号、项目、运行时、存储、更新、数据库和测试提供模块导航。源码目录重构另行设计。
- GitHub默认分支的workflow展示名需在精确Git计划中同步，保持workflow文件路径及手动入口身份。

## 本地验证条件

本地八来源性能夹具采用合成签名，复用迁移验收留下的四个真实历史镜像，候选固定为迁移已验证的联合清单。串行与并发使用完全相同的八来源。该测量用于调度等价与故障收口；正式CI最近八个真实发行和跨runner缓存仍按推送后验证收口。

用户进一步讨论全量Rust重写后明确暂不考虑，当前技术栈与目录物理结构保持现有方案。

## 默认分支手动入口注册

只读核对发现 main 仅有 v3-release.yml，尚无 v3-build.yml。为提供可见的手动构建入口，在独立 main 检出目录同步 .github/workflows/v3-build.yml 与共享cache action，并将该分支的 build job 限定本仓 v3/flower2api ref；main 本身的手动选择保持跳过。同步 release 的展示名与输入说明。精确Git计划列明 main 的三个文件，选择实际目标分支后继续由该分支源码执行。

- 运行时本地日志页的浏览器标题与页头品牌同样统一为flower2api，保留原页面状态、接口和CCRB参数。

- 运行时页面验收发现原浏览器断言把未知头x-future-ui预期为保留；现有源码、协议规范和单测均要求删除。同步该失效断言为删除及固定原因，沿现有协议验证。

正式CI的最近八个真实发行双路演练由下次管理员明确发版承接为上线后验证，本任务保持零正式发行副作用。当前完成条件包含本地等价/故障收口与推送后的跨runner缓存命中、完整冷热耗时记录。
