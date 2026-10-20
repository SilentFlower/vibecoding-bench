# 环境物理特征面板设计

## 入口与数据

- 扩展现有 GET `/api/environments` 的只读详情摘要；新增 POST `/api/environments/{environment_id}/physical-features/refresh` 进行显式本地采集，沿用管理桥鉴权。
- 用独立 `orchestrator/physical_features.py` 定义白名单字段、探针输出校验、保存配置映射和比较；AccountRuntime 负责实际归属、锁及 Docker 访问，main 负责 DTO 和 HTTP 状态。
- root 私有 `runtime/physical-features.json` 记录 schema、environment_id、generation、container_id、UTC observed_at 及白名单实测字段，通过现有 atomic_json 发布。总大小与单字段长度有界，不保存环境变量、命令正文或凭据。
- 列表读取只加载已有记录，不 exec、不 ensure、不生成指纹。缓存代次或容器归属不符时标记为旧观察，不能作为当前实测。

## 采集

复用 owner → profile → environment 锁序，非阻塞获取；维护占用、CLI 正忙、容器停止/缺失/归属不符时返回原因，不唤醒或重建。探针在已归属的 CLI 容器内以账号用户执行，只读文件和安装状态；子进程及 Docker 调用都设置有限截止，输出超限或结构错误拒绝覆盖上次合法快照。

操作系统来自 os-release，内核和 CPU 型号来自 CLI 实际可见接口；MAC 取同一网络命名空间的实际接口信息；DMI 从既有两目录白名单读取；Shell、包管理器、工具链来自本地安装状态。machine-id 只显示存在性。

RAM 复用账号镜像已安装的 `process_metrics.memory_limit`；明确无限制才显示未限制，失败显示未采集。CPU 可见逻辑数/亲和性与可选 cgroup 配额分别标注，不能把宿主逻辑总数当独占核数。根文件系统只显示采集到的类型，不推测磁盘容量。

## 展示

- 环境卡片保留原维护动作，增加可展开详情及“刷新实测”。配置和实测分列，显示采集时间及一致/不一致/未采集；没有配置字段时只显示观察值。
- 字段涵盖 PRD 所列物理特征；停止环境显示已存配置及上次观察并明确时间。差异仅展示，不自动校正画像。
- 所有文本转义，沿用原生 JS/modal 和明暗主题样式，窄屏支持滚动；不改变账户、登录或维护许可。
- 使用 row.fingerprint 的有效时区，P2 接入后在同一位置展示当地时钟和窗口摘要，草稿没有账号配置时明确标识。

## 验证与兼容

覆盖没有快照、有效快照、旧代快照、坏格式、读取失败、停止、占用和配置差异；实际 Docker 验证 DMI/CPU/内核来源、cgroup RAM 及只读采集的身份摘要保持。独立 API 长流及其它账号不受影响。

无数据库 migration。旧环境缺 computer_profile 时显示缺失，不能调用画像准备路径补齐；旧镜像或不支持字段明确未采集。回滚忽略 runtime 中的新观察文件即可。
