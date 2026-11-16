# 原生280/293自动选择

同一账号的原生后端使用历史配置键 `request_backend=native293`。管理页面显示“280 / 293 自动匹配”。客户端模式精确匹配原始 Claude UA；普通 API 的其它已准入版本沿配置默认画像选择，出厂为293。账号模式沿账号最终软件画像。完整原生正文的 billing 必须匹配本次冻结的执行版本，冲突返回422。

## 安装与来源

| 源版本 | 固定官方源SHA256 | 安装路径 |
| --- | --- | --- |
| 2.1.280 | `1e08503dbdf3c2cb0d706d32f3408277388d1c76ef108673e8fe42c1b322925b` | `/usr/local/bin/ccrb-runtime-280` |
| 2.1.293 | `8968405e26db478af44eabc4635ab5ca557057b702a54460a59c13e1b253e978` | `/usr/local/bin/ccrb-runtime` |

| 制品 | 分发字节 / SHA256 | 执行映像字节 / SHA256 |
| --- | --- | --- |
| 280内置 | 27097232 / `3666887daafb75290597be37b84a1c5cfd92ab664de8bb862c79a501ea75deed` | 111595592 / `2b64ee7d8f0863a37bce90800226bda102387e5cff082f947b2b71e66d9a38e7` |
| 293 beta.6 | 27388048 / `fce50a30d739dbc614e450d4d1913208fa35c6373c4f07a3986657393a99261e` | 112843960 / `564019c9560e960e96875c9663975491534b27c789ea3d23e5c13309ff293c79` |

两份分发体合计54485280字节。每个执行体独立保持单文件部署合同。来源、Bun revision和资源布局按版本核验，外部manifest不能授信未知制品。

CI沿 `.github/actions/flower2api-native-runtime` 从固定npm 280归档核对SHA512，再核对官方文件SHA256，调用已有隔离构建器，最后核对固定分发SHA256。缓存命中也执行最终校验。构建工作流使用Ubuntu24.04及固定Bun1.3.14。新构建内容造成摘要变化时须重新完成验收并更新消费身份和缓存键。

本地可在仓库根准备同一制品：

```bash
python3 services/runtime/scripts/prepare-ci-runtime.py --directory /绝对路径/native280
export V3_NATIVE_RUNTIME_280_ASSET=/绝对路径/native280/ccrb-runtime
```

准备脚本需要Linux x64、Bun依赖、GCC和创建网络命名空间的权限。已有产物也可直接通过上述环境变量传给联合构建。293沿原固定beta.6下载路径，`V3_NATIVE_RUNTIME_ASSET`可提供同摘要本地文件。280公共独立发行沿后续发行流程处理。

## 共享容量与隔离

新版账号镜像声明 `vibebench.native-runtime-versions=2.1.280,2.1.293`，编排端据此生成受信安装表。旧标签缺省提供293。每账号保持唯一并发、RPM、凭据所有者和物理容量，两版的活动、启动及空闲进程合计遵守原 `max_workers`。映像、暖进程、准备操作、模板和内核代次按版本隔离。凭据、代理或环境身份变更统一撤销两版旧代空闲进程。

有限双版本sender的exec最低预算为 `384 + 192 × 2 × 标准并发` MiB。标准并发3对应1536MiB，标准并发4对应1920MiB。账号总RAM还需覆盖network256MiB和CLI最低512MiB。无限模式沿原明确零预算语义。293单版本历史布局继续使用256MiB池基础份额。恢复预算沿独立CRIU政策校验。

容量紧张时先退役其它版本空闲进程或取消其补位。新进程等待真实退出归还许可。额外暖进程空闲300秒回收，账号各版合计保留最近使用的一个基础暖进程。

## 准备、升级及诊断

私有请求、准备、取消和升级目标使用 `source_version=2.1.280|2.1.293`。历史省略值表示293；293报文继续省略该字段。安装缺失返回受控503，各版能力独立报告。签名清单的源版本及源SHA、分发摘要、执行映像和实际握手联合核验。

管理接口省略版本继续指向293。内核操作冻结所选版本及CAS；升级记录分别为 `native-kernel-upgrade.json` 和 `native-kernel-upgrade-280.json`。两版共用账号维护门禁，单版激活或回滚只改变所选配置及子池。准备快照按版本独立校验环境、代次、内核代次和45秒新鲜度。请求诊断保存实际源版本与对应 `native280_cc_prepared` / `native293_cc_prepared`。

280采用自身Bun原生fetch与CCH路径。280的turnPosition及turnOrigin沿原版本省略语义。280的side_reply类别明确返回422。280的CRIU模板尚处独立准入阶段，当前通过同版受限exec启动。293固定TLS模拟verifier仅接受293；真实TLS旁路探针按两版执行映像摘要定位各自SSL_write偏移。

采集器源码为 `native/tls-observer`，镜像消费 `images/v3/tls-observer`。开发验证使用明确的development清单。正式导出依照采集器README要求，在canonical源码提交且干净后生成带真实revision的正式清单，再进入镜像构建。

验收记录见仓库任务 `.trellis/tasks/11-16-native-runtime-280/research/acceptance.md`。测试使用合成凭据、本地TLS和隔离网络命名空间。
