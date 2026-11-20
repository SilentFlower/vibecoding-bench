# 实施计划

## 执行方式

默认inline，首次实现前由trellis-route确认路由。按真实类型和调用者修改，保留并行任务变更。

## 顺序

1. [x] 阅读本任务清单、包规范和相关DTO，冻结本轮精确差异及旧接口行为。
2. [x] 实现平台内置信息投影、配置归一化和Rust固定装载边界。
3. [x] 实现旧root/per-version选择迁移，验证归属、活动、租约、停止状态和幂等。
4. [x] 接入平台重建／恢复及历史回退，在升级维护阶段完成目标安装表迁移，将登记完整、制品核验和发送器就绪纳入升级完成条件；收口独立挂载与原生发行信任根依赖。
5. [x] 收口API、独立执行逻辑、页面操作和轮询，保留只读状态及必要内部兼容投影。
6. [x] 完成本仓库293官方准备、双版CI缓存和staging，核验所有消费者身份。
7. [x] 完成定向与集成验证，再按实际diff执行Check-All。
8. [x] 同步规范并完成已确认的业务提交与推送，进入任务记录同步。

## 主要文件

- 独立兼容入口：apps/legacy-web/environments.js、app.js、index.html，同步只读展示与静态版本参数。
- 前端：runtime/EnvironmentKernel.vue、runtime/runtimeApi.ts、RuntimeEnvironments.vue。
- 编排：native_sender.py、native_kernel_upgrade.py、native_kernel_releases.py、account_isolation.py、account_runtime.py、main.py、system_updates.py；CPU／内容采集／CRIU的关联调用。
- Rust：native_contract.rs、native_runtime.rs、native_release.rs、runtime_transport.rs、handler/router.rs、凭据归属中的退役专用许可及跨平台实现。
- 构建：prepare-ci-runtime.py、flower2api-native-runtime/action.yml、manage.py、Dockerfile的必要配套。
- 宿主交付：检查install_system_updater.py、system_release.py的固定源码依赖；对应测试和规范。

## 验证

### 迁移和接口

- Python unittest覆盖native sender、历史迁移、account runtime、system updates、CPU／CRIU／内容采集和退役接口。
- 旧beta.6／beta.7、两份旧记录、root/per-version配置均收口；旧代码读取结果为内置；重复执行一致。
- 长流排空、停止保持、旧中断操作、外来租约和未知状态分别验证。
- 回归截图场景：旧sender只登记293，升级至双版镜像并完成验收，登记养号活动后分别发送首笔293和280请求；断言API成功、环境代次和容器ID保持，布局重建调用数为零。
- 补充升级前养号占用的排空／超时恢复，以及历史单版目标的能力匹配。
- 旧接口已鉴权410、未鉴权沿原规则拒绝，下载／切换／租约mock调用数为零。

### 实际执行

- cargo fmt --check；cargo test --locked --lib。
- 扩展现有cc2api-native真实消费者夹具，使用已接纳两版制品验证历史配置、源版本匹配、混合容量和实际身份。
- 既有signature fixture核对同账号400修复与会话首发复用；保留工具历史、TLS和CRIU合同。
- 场景使用合成身份和隔离回环。

### 构建、页面、更新

- 本仓库冷构建293、复用280，核对已接纳摘要；覆盖报告、来源和缓存异常。
- 旧仓库路径阻断条件下完成双版CI准备和镜像staging。
- npm --prefix apps/web run build；扩展环境页夹具验证只读双版状态、旧观察、独立按钮退役和明暗移动布局。
- 源布局、工作流、数据库定义、系统更新合同测试。
- 在独立合成Docker环境扩展系统更新／回退，核对旧选择迁移、长流、停止账号和真实内核身份。

## 恢复点

- 先验证旧租约与迁移失败分支，再接入生命周期。
- 历史字段与deny_unknown_fields联合验证；旧平台回退重点核对文件回写顺序。
- 原生发行信任根与平台更新信任根分别核对；检查宿主导入闭包。
- 并行文件以本轮行为差异为范围。正式发布和生产变更由后续流程负责。

## 实施中的验证修正

- 旧转发原始字节夹具先完成服务初始化，再启动网络接收超时，避免初始化耗时占用10秒转发预算；保持原始字节及超时断言。
- 固定内核冷构建使用本任务基线源码快照。当前共享工作区的其他runtime源码变动已触发固定摘要拒绝；并行任务的新版内核准入沿其原任务处理。

## Check-All修复

- CHK-001：在受控换绑门禁内、停止旧发送器后归档全部终态内核记录；提交前中断可重试，提交后新绑定采用内置选择。未知归属、迁移日志和未完成维护先拒绝。
- FBK-001：退役候选下载标记退出维护门禁，启动恢复保留取消审计；真实迁移及维护保护保持。
- CHK-002：升级演练使用ensure返回的当前环境记录，再补跑实际升级、双版请求和回退。
- 隔离演练的网关和发送器沿正式verification-backend使用v3-verification特性，并在Bookworm中构建以匹配测试底座glibc；临时CA由既有隔离分支核验。

## 修复后的验证事实

- Python功能回归158项、更新合同50项通过；新制品相关定向复核31项通过。
- Rust完整回归通过：库测试865项及集成测试；依赖外部独立数据库的既有忽略项沿原约定保留。
- 当前源码两版冷构建、缓存命中和staging通过，分发摘要分别为21e7c3／9a5eb4。
- 真实双版消费者18笔请求、混合并发峰值6通过；Docker升级／回退11场景通过，真实模型调用为0。
- 两套页面只读内核与资源维护回归、前端构建通过。
- 独立提交快照复核通过：Python164项、Rust库859项及全部集成测试、历史选择归一化定向测试、前端构建；快照基于24de2b39，保留共享文件中的其他任务改动。
