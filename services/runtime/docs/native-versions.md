# 原生280/293自动选择

同一账号的原生后端使用历史配置键 `request_backend=native293`。管理页面显示“280 / 293 自动匹配”。客户端模式精确匹配原始 Claude UA；普通 API 的其它已准入版本沿配置默认画像选择，出厂为293。账号模式沿账号最终软件画像。完整原生正文的 billing 必须匹配本次冻结的执行版本，冲突返回422。

## 安装与来源

| 源版本 | 固定官方源SHA256 | 安装路径 |
| --- | --- | --- |
| 2.1.280 | `1e08503dbdf3c2cb0d706d32f3408277388d1c76ef108673e8fe42c1b322925b` | `/usr/local/bin/ccrb-runtime-280` |
| 2.1.293 | `8968405e26db478af44eabc4635ab5ca557057b702a54460a59c13e1b253e978` | `/usr/local/bin/ccrb-runtime` |

| 制品 | 分发字节 / SHA256 | 执行映像字节 / SHA256 |
| --- | --- | --- |
| 280内置 | 27097232 / `db7848ddd74a9d618c8e3d45ad0e54f71705f3e6ae25bbaccf5b83abf27534cb` | 111599688 / `431aede03d82d6d300da7343f0fb04f983cba2fac83474a6e532f721b0d7a61e` |
| 293 beta.7 | 27392144 / `a885ac62ee14888b1f637f00bdb98d07fa43dab0f62735ceb731c7116396431b` | 112848056 / `6296aa4f164b8018f6f614915befd347a0dbd73f674ace20534e91947eba4434` |

两份分发体合计54489376字节。每个执行体独立保持单文件部署合同。来源、Bun revision和资源布局按版本核验，外部manifest不能授信未知制品。

CI沿 `.github/actions/flower2api-native-runtime` 从固定npm 280归档核对SHA512，再核对官方文件SHA256，调用已有隔离构建器，最后核对固定分发SHA256。缓存命中也执行最终校验。构建工作流使用Ubuntu24.04及固定Bun1.3.14。新构建内容造成摘要变化时须重新完成验收并更新消费身份和缓存键。

本地可在仓库根准备同一制品：

```bash
python3 services/runtime/scripts/prepare-ci-runtime.py --directory /绝对路径/native280
export V3_NATIVE_RUNTIME_280_ASSET=/绝对路径/native280/ccrb-runtime
```

准备脚本需要Linux x64、Bun依赖、GCC和创建网络命名空间的权限。已有产物也可直接通过上述环境变量传给联合构建。293沿原固定beta.7下载路径，`V3_NATIVE_RUNTIME_ASSET`可提供同摘要本地文件。280公共独立发行沿后续发行流程处理。

## 共享容量与隔离

新版账号镜像声明 `vibebench.native-runtime-versions=2.1.280,2.1.293`，编排端据此生成受信安装表。旧标签缺省提供293。每账号保持唯一并发、RPM、凭据所有者和物理容量，两版的活动、启动及空闲进程合计遵守原 `max_workers`。映像、暖进程、准备操作、模板和内核代次按版本隔离。凭据、代理或环境身份变更统一撤销两版旧代空闲进程。

普通exec的双版及历史293单版配置均不按固定MiB公式限制并发。有限sender继续使用显式正数额度，账号总RAM还需覆盖network256MiB和CLI最低512MiB；无限模式沿原明确零预算语义。恢复预算沿独立CRIU政策校验，恢复额度不足时走普通exec。过小有限额度的真实资源不足沿原准备或启动错误处理。

共享范围是同账号同版本的执行映像，每个worker仍有独立堆、SDK及请求缓冲，各账号分别持有池。280/293执行映像合计约214MiB，属于映像字节数。既有293共享池六路cgroup峰值约646MiB、回收后约189MiB；280/293混合池峰值需独立测量，配置额度与实际占用分别报告。

容量紧张时先退役其它版本空闲进程或取消其补位。新进程等待真实退出归还许可。额外暖进程默认空闲120秒回收，账号各版合计保留最近使用的一个基础暖进程，执行映像缓存继续保留。系统设置 `native_idle_timeout_secs` 支持30–3600秒，后台巡检将同一账号级策略同步到两版池，更新会唤醒旧回收计时器重新计算期限。

## 准备、升级及诊断

私有请求、准备、取消和升级目标使用 `source_version=2.1.280|2.1.293`。历史省略值表示293；293报文继续省略该字段。安装缺失返回受控503，各版能力独立报告。签名清单的源版本及源SHA、分发摘要、执行映像和实际握手联合核验。

管理接口省略版本继续指向293。内核操作冻结所选版本及CAS；升级记录分别为 `native-kernel-upgrade.json` 和 `native-kernel-upgrade-280.json`。两版共用账号维护门禁，单版激活或回滚只改变所选配置及子池。准备快照按版本独立校验环境、代次、内核代次和45秒新鲜度。请求诊断保存实际源版本与对应 `native280_cc_prepared` / `native293_cc_prepared`。

280采用自身Bun原生fetch与CCH路径。280的turnPosition及turnOrigin沿原版本省略语义。280的side_reply类别明确返回422。280的CRIU模板尚处独立准入阶段，当前通过同版受限exec启动。293固定TLS模拟verifier仅接受293；真实TLS旁路探针按两版执行映像摘要定位各自SSL_write偏移。

采集器源码为 `native/tls-observer`，镜像消费 `images/v3/tls-observer`。开发验证使用明确的development清单。正式导出依照采集器README要求，在canonical源码提交且干净后生成带真实revision的正式清单，再进入镜像构建。

验收记录见仓库任务 `.trellis/tasks/11-16-native-runtime-280/research/acceptance.md`。测试使用合成凭据、本地TLS和隔离网络命名空间。
