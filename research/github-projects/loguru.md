# Loguru：真实 GitHub 项目研究

研究完成：已核对来源许可、固定真实源码，复用完整适用原生基线并重新运行普通日志业务场景，形成[20项独立增强提案及验收边界](./loguru-roadmap-20.md)。**仅研究，未实施路线、未冻结独立验收、未接入正式库。**

## 来源许可和真实源码

官方仓库[Delgan/loguru](https://github.com/Delgan/loguru)，固定完整提交[`bce5dfd3b435b1d1658507d7e095ad7a9919bf1c`](https://github.com/Delgan/loguru/tree/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c)，源码版本0.7.3。官方元数据、revision与实际检出一致。已读LICENSE为MIT，保留版权、许可与免责声明。跟踪**313文件、1,545,464字节**，Python文件合计**20380行**（含大量原生测试与示例），venv **128,536,134字节**。

已读取公开Logger.add/remove/complete/opt/bind/contextualize/patch/level/activation/configure/parse和实际_log构造链、Handler队列与序列化、各sink生命周期、FileSink轮转/压缩/retention、RecordThread/Exception、异常帧筛选、ctime平台fallback、公开stub与相关原生测试。未将logger重写成简化工程，也不把私有字段当已经稳定的公开API。

## 原生基线与版本成本

证据根`.deploy/github-100-research/resume-main/loguru/`。原生测试在镜像`ghcr.io/silentflower/vibebench-v3-account:v3-ci-39482854683-1`、UID1000、network none、768MiB预算运行，源检出只读，复制到本轮可写测试工作区；私有账号HOME未挂载。实际镜像Python **3.12.15**，已单独读取同一镜像sys.version并保存runtime-versions.json；安装venv和本轮业务观察的宿主Python为**3.12.3**，两者不混写。

完整原生集合包含mypy YAML用例：**1679通过、0失败、0错误、46普通条件跳过、0 xfail**，墙钟**141.703秒**、pytest**136.764秒**、峰值RSS**169,384KiB**，无OOM，运行容器已移除。46项跳过是Windows专用实现、当前Python缺少的template-string等条件，逐项见baseline-result.json.skip_details和原始log/XML。未覆盖其他Python/OS；未把跳过项当通过。

基础安装21.042秒，后续补依赖有install-completion.log；最终freezegun **1.5.0**、mypy **2.3.1**等版本见requirements-frozen.txt。此前依赖不齐、只读副本或tmpfs预算不足等失败保存在dependency-first-attempt/readonly-first-attempt/tmpfs-second-attempt/runner-prelude-error，不覆盖为成功。最终完整通过证据已复核，本轮未重复长测试。额外运行只读镜像版本查询并非重新跑基线。

## 实际普通业务场景与路线依据

observe.py在独立宿主进程从固定source/loguru导入，导入路径及host_python写入observations-result.json。bind(item_id=3)输出中文商品保存消息；本地临时文件实际触发轮转，文件内容合计保留三条普通商品事件；async sink经await complete处理一条本地事件。无外部日志平台、网络服务、凭据或生产数据。

20项观察分别支持运行时更新/配置快照、sink资源作用域、局部静默、收尾截止时间、显式队列容量/线程后端、序列化回调/结构化异常帧、按record本地文件路由、独立归档目录、栈帧呈现筛选、轮转文件信息、retention错误策略、native线程编号、async任务元数据、模块缩写、多行前缀、逐参数lazy及事务配置替换。所有条目均为研究者增强提案，没有将默认机制未承诺的保证称为缺陷。

原版配置失败会关闭旧sink并留下第一个有效新sink；这是configure文档定义的顺序，路线明确新增事务模式。retention PermissionError仅通过受控本地IO注入展示失败路径，**没有宣称复现Windows原场景**。队列使用SimpleQueue，报告只证明没有公开的记录数容量/策略，不推断它必然无界内存。JSON text已有完整异常文本，提案仅增加结构化帧。多个rotation条件、固定活跃文件+时间归档、全局extra、deepcopy独立logger与async收尾等现有能力都明确排除，未拿旧issue标题凑数。

## 证据和重跑

证据根含官方repository/issues元数据、完整revision、安装与冻结依赖、原生baseline-result/log/XML、runtime-versions.json、observe.py及observations-result/log、roadmap-20.json、review-result.json和evidence-sha256.json。20步JSON封存唯一ID、真实模块/回归路径、每步原版观察、验收与依赖；所有上游源码保持干净。

在项目根重跑普通业务场景：

```bash
LOGURU_AUTOINIT=0 PYTHONDONTWRITEBYTECODE=1 .deploy/github-100-research/resume-main/loguru/venv/bin/python .deploy/github-100-research/resume-main/loguru/observe.py
```

完整基线由run_native.py的baseline入口、原tests参数与768m预算重跑，依赖/测试工作副本及mypy入口按该脚本准备；调用需使用已有控制环境`.deploy/github-100-research/resume-main/control/bin/python`的Docker SDK，普通宿主python3未安装该SDK。本轮同镜像版本查询第一次因此失败，随后使用正确控制环境成功，未改变基线。重复取证前先归档本轮原日志/XML并确保不会把旧XML误读为本轮结果。

异机clone官方URL并detached checkout固定commit，按冻结依赖创建venv，保留freezegun/mypy版本，再准备等价隔离运行环境。当前本地镜像/venv和证据位置不是跨机器可用性保证；冻结验收前仍需离线依赖准备。研究完成与验收可用、模型完成、生产部署分开统计；本轮未改正式库或产品代码，未提交/推送/部署/向上游发消息。
