# Claude Code 2.1.293 实施计划

## 1. 持续完成证据采集

- [x] 核对线上版本、capture DTO、题库文本、账号代理与正式链路。
- [x] 完成 Opus bypass/Auto/Plan 三轮，逐请求验证 18 条 billing 的 CCH 与后缀。
- [x] 完成账号 15 的 Sonnet bypass/Auto/Plan，累计六轮、29 条 billing 全部复算通过。
- [x] 完成 Sonnet/Fable 六模式及账号 15 的 Haiku 5.5 基线/Auto/Plan/Manual，累计十九轮、83 条 billing 全部复算通过；已核对四模型的 Auto/Plan safeguard 工具关联。
- [x] 完成 Haiku acceptEdits/dontAsk，两轮各 7 条 billing 全部命中；累计二十一轮、97 条复算及串行/清理审计通过，Sonnet/Fable/Haiku 六模式齐备。
- [x] 建立串行、冷却、账号轮换和异常暂停的受限运维记录；不发送自定义提示词。
- [x] 汇总已完成轮次的启动间隔、终态、原始链路、镜像、提示词和工具关联；复查发现首轮 Opus 的 fallback default 分支已实际采到，补充精确 beta 顺序与 CCH 证据。
- [x] 修正运维复算器的会话分组：Haiku Plan 的交错会话按响应身份逐链校验；保留旧复算结果并重查全部十八轮，77 条 billing 全部命中，不改变产品代码或 hash 规则。
- [x] 用户继续采集时保留已有矩阵与冷却记录；因既有养号阻塞，为剩余六轮安排一次最多 60 分钟的续采，达到新上限后停止，不重复已有样本。
- [x] 账号 22 既有养号结束并复查后，完成新 Opus 基线及 manual/acceptEdits/dontAsk 四轮；Sonnet/Fable/Haiku 六模式已完成。
- [x] 用户追加 Fable 5.1：以账号 22 完成 `claude-fable-5-1[1m]` 的六种权限模式，逐请求核对 wire 模型、1M beta、fallbacks 与 CCH；本组全部主请求为 64000 token，未出现 context-1m 或 fallbacks。
- [x] 汇总每个 run 的真实 UA、镜像、模型、effort、模式、启动间隔、终态和容器清理。
- [x] 逐请求复算全部 CCH/后缀，比较 beta 顺序、关键 body 字段与 safeguards/SSE；整理脱敏协议报告。

## 2. 收敛规划并复核 Brief

- [x] 根据已验证样本明确画像边界、软件身份和准入关系；按用户截图澄清改为默认 293、通过允许/禁止配置使 280/293 可用，保留 260 画像，撤回删除与专用强制迁移计划。
- [x] 执行 PRD 收敛，核对需求、边界、验收映射及待采集的技术检查点。
- [x] 按默认 293、配置准入 280/293、保留 260 能力的澄清刷新并完整展示 Brief；用户确认后已运行 task.py start，任务进入 in_progress。
- [x] 进入 trellis-route(target=implement)，命中任务级 inline 路由；按 trellis-before-dev 完整读取适用协议、后端、前端、部署和共享指南，核对账号 DTO 与画像结构。

## 3. 实现 293 画像

- [x] 开始修改画像处理代码前，完成第 1 节的剩余采集和全量复算；失败项明确记录，证据不足时停止相关实现，不填写猜测参数。
- [x] `cc2api/src/service/version_profile.rs`：新增独立 identity、精确模型与辅助请求描述，注册 293 的 UA 和版本选项，出厂默认改为 293；保留 260/280 注册、UA 映射与输出。
- [x] 根据 Fable 5.1 的实际 293 样本决定其独立子画像、fallback/CCH 和 bootstrap 兼容处理，保留未采到分支的明确边界。
- [x] `cc2api/src/service/rewriter.rs`：只在已验证分支扩展 SDK/beta、标题分类、CCH、续轮后缀、字段顺序和后台端点；保留未知字段与 SSE 字节。
- [x] 根据实际调用需要同步 gateway 的请求分类、bootstrap 与 headers；继续复用请求冻结、账号副本和版本缓存隔离机制。
- [x] `src/store/settings_store.rs`、`src/store/db.rs`、`src/handler/router.rs`：默认改为 293；仅迁移明确的旧出厂组合，保留显式 260 画像和自定义准入；保存目标允许/禁止规则时维持事务及原子热刷新，覆盖 SQLite/PostgreSQL。
- [x] `web/src/components/Settings.vue`、必要的 API 类型与账号页文案：加入 293 描述，更新初始值和重置按钮，保留 260 选项；展示允许/禁止配置如何使 280/293 可用以及准入/默认关系，保持基础版本的含义。
- [x] README 与协议规范同步已验证行为；保留用户既有未提交抓包规范改动，不顺带整理或提交。Phase 3.3 已更新三份 cc2api 规范，反向核对代码、beta、测试签名与链接通过。

## 4. 验证

- [x] 使用脱敏 fixture 和独立复算期望值覆盖新模型、SDK、beta 顺序、CCH、UTF-16 初始后缀与线程续轮。
- [x] 验证 Haiku 5.5 标题不误分类，自动旧 Haiku 探测仍正常。
- [x] 验证 260/280 的 wire 回归、293 精确 UA、默认 293、非法/缺失/未来 UA 回退、请求体版本不影响选择；保留 260 的映射和可选配置。
- [x] 验证三版本并发、账号重试与热刷新不污染请求画像，账号持久身份/容量不变、缓存隔离有效。
- [x] 验证目标允许范围 `2.1.89-2.1.293`、禁止范围 `2.1.89-2.1.279,2.1.281-2.1.292` 下只放行 280/293；260、279、281、292、294 拒绝，默认画像不能绕过禁止规则；自定义准入及显式 260 配置保留，迁移幂等，账号模式旧策略保留。
- [x] 运行 `cargo fmt --check`、`cargo test`、`cargo test cch` 和 `npm run build`；正式 Check-All 后更新规范。四项命令与规范校验均已通过。
- [x] 核对原始证据仅在远端、受限权限正确，Git 中不存在凭据与真实完整正文。

## 5. 交付

- [x] 展示实际 diff 与验证结论。需要提交时进入 trellis-push 的精确范围确认；需要上线时另行遵循部署 SOP。
- [ ] 未完成矩阵、复算不通过或字段证据不足时，保留实际进度与恢复位置，不部署、不宣称完整 293 画像已验证。

## 已执行验证记录

- `cc2api/` 的 `cargo test`：618 项通过，独立 PostgreSQL 场景默认忽略；随后以本地临时 PostgreSQL 显式执行该场景，1 项通过。临时容器已移除。
- `cargo fmt --check`、`cargo test cch`（25 项）及 `cc2api/web/` 的 `npm run build` 均通过。子仓及父仓 `git diff --check` 通过。
- 独立合成 fixture 覆盖 11 组 CCH/后缀、22 种原生消息 beta 形状和 6 个后台端点；真实正文及身份未导出。
- 本地浏览器使用独立临时 SQLite 和合成账号，实际验证预设仅改表单、保存/刷新回显、UA 保留、260 选项保留、账号模式范围只读和账号基础版本；无页面异常，无生产请求，服务及测试库已清理。
- 全面核对发现账号模式也会迁移旧出厂组合，已按设计补上客户端模式条件，并用 SQLite/PostgreSQL 验证账号模式 260/280 保留及幂等；修复后完整 Rust 回归再次通过。
- 验证日志及页面预览仅在本地忽略目录 `.deploy/293-*`；用户既有抓包 SOP SHA256 保持 `26cc5ba38271d857dcac1542327cc7499067133cea86a91f6701d421c7b01f2b`。本轮未部署、未提交 Git。
