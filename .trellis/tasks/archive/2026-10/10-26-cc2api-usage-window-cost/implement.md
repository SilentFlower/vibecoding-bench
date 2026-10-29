# 实施与验证计划

## 顺序

1. [x] 已完整展示 Brief，用户确认并补充“随着刷新”更新窗口统计；同步该决定后执行 `task.py start`、进入 `trellis-route(target=implement)`，按解析结果加载 `trellis-before-dev`。本计划不要求子代理。
2. [x] 对照参考仓库实际价格解析与计价方法，提取有来源版本的 Claude 快照；定义用量记录、窗口统计 DTO 和一次性记录上下文，补定价差异样例。
3. [x] 新增统计 store、SQLite／PostgreSQL 幂等 schema、索引、统计启用起点和时间裁剪；验证独立读取、重启恢复、窗口边界及批量汇总。
4. [x] 通过 `main.rs`／service／router 既有构造方式注入统计能力；所有新增共享构造函数同步现有测试 fixture，不使用猜测字段。
5. [x] 接通 `SlotGuardBody`、非流缓冲探针等真实 messages 调用的用量记录；独立于自动遥测，覆盖 JSON、分块 SSE、压缩、错误和 Drop。真实调用一次记录，本地 mock／缓存命中不计费。
6. [x] `GET /admin/accounts` 批量附加独立统计字段；同步 `web/src/api.ts` 后改造 Accounts 的通用 5h／7d 展示及未知／待更新状态，不改变现有 Fable／Sonnet 含义。
7. [x] 运行定向集成验证及必要全量检查；已完成 inline 全面 Check-All，R1～R7 通过，未发现 CHK／FBK；已同步窗口费用规范，按确认范围不执行提交／推送。

## 预期文件范围

- 子仓：`src/model/` 中所需统计 DTO，`src/store/db.rs` 与新增用量 store，`src/service/gateway.rs` 与必要的共用解析／价格模块，`src/main.rs`、`src/lib.rs`／模块导出、`src/handler/router.rs`、`web/src/api.ts`、`web/src/components/Accounts.vue`，以及相应测试和紧凑价格数据。
- 父仓：当前任务材料；完工阶段按实际新增契约评估 `.trellis/spec/cc2api/backend/`、`frontend/` 的必要同步。
- 不改参考仓库，不改 v3 orchestrator 或其它活跃任务。

## 定向验证

- 定价：输入／输出／缓存读、5m／1h 分项及残余总写量、已知别名、Fable 与新旧 Claude、fast／priority／长上下文；未知模型和负数／溢出／非有限值安全拒绝。以 sub2api 对应公式的具体预期金额为断言，不仅检查字段自身相加。
- 持久化：schema 重跑幂等、同唯一键两次 finalize 只写一条、已提交记录跨连接／重启可见；并行写入不丢计数、按时间保留完整周数据。
- 时间：固定 now 验证两个 reset、请求恰在边界、跨 reset 长请求、毫秒／UTC、过期／非法／缺失 reset 的滚动降级和来源标记。
- 网关：合成 JSON、跨 frame SSE、压缩响应及截断；关闭遥测时仍记账；正常 EOF、body error、客户端断开不重复，已有部分 usage 会标记不完整；本地 mock、非流缓存命中、count_tokens、手动额度查询和无消费重试不增加费用。
- API／页面：合成账号和请求写入隔离数据库，通过管理 API 核对窗口统计，检查费用两位小数、紧凑布局、旧字段兼容、未知／过期／未定价／首周期不完整及正常估算。沿用项目已有可用浏览器或本地预览方式，不搭建无关测试框架。
- 估算：有效 10% 和完整 $12.50 样本得到 $125.00；零百分比、未知、过期、缺价、部分采集或周期覆盖不足均不显示估算。
- 刷新：重复读取／刷新账号不删除记录，两个官方窗口分别推进后只展示新周期对应数据。

## 必须执行的检查

```bash
cd cc2api
cargo fmt --check
cargo test --locked
```

```bash
cd cc2api/web
npm run build
```

定向测试名称随实际代码确定并写回证据；只在相关变更或失败需要时重复全量检查。规划阶段仅修改文档，不提前运行产品测试。

## 回滚与交付边界

新增表不破坏旧版本读取，可回滚本轮代码而保留统计记录。实现前后均检查父／子仓 diff；不触碰真实账号、线上库、生产部署或 Git 提交／推送。本地验证只使用隔离合成数据。

## 已执行的定向验证

- `cargo test --locked --lib usage`：41 项相关测试通过，包含后端窗口、分页 API、已有被动额度与共享解析回归。
- `gateway_usage_records_real_responses_once_without_telemetry`：真实本地 HTTP 上游覆盖 JSON、SSE 分块、gzip、取消、首次非流缓存调用、缓存命中与 count_tokens；5 次模型调用只落 5 条记录，缓存命中和计数接口不增加消费。
- `cargo fmt --check`、`cargo test --locked`、`npm run build` 与本地二进制构建均通过；最终完整回归 661 项通过、1 项既有 PostgreSQL 环境测试跳过。新 SQL 已静态核对双数据库类型、占位符、聚合结果与幂等迁移兼容性，未连接真实／生产数据库。
- `/tmp/cc2api-usage-ui-verify.py`：隔离 SQLite 与真实管理 API、Chrome 桌面／390px 页面，验证刷新保留、5h 独立换周期、7d 旧周期保留、未知／过期状态、零自动 usage POST、零浏览器异常；全部通过。
- 价格快照位于 `src/service/claude-pricing.json`，随现有 Docker 构建的 `COPY src` 一起进入编译；没有新增构建目录依赖。
- 快照与参考仓库 26 个目录型号逐字段比较通过；新增已知别名、明确 Claude 兜底及长上下文规则一起由定价测试验证。
- Update-Spec 结果为 `written`：后端 `settings-database.md` 新增六节窗口费用契约，前端规范增加权威链接；规范 diff 与六节／链接校验通过。
- 最终证据：`/tmp/cc2api-usage-full-tests.log`、`/tmp/cc2api-usage-web-build.log`、`/tmp/cc2api-usage-build.log`、`/tmp/cc2api-usage-ui.log`；页面截图 `/tmp/cc2api-usage-desktop.png`、`/tmp/cc2api-usage-after-reset.png`、`/tmp/cc2api-usage-mobile.png`。
- 本轮按已确认的范围排除发布部署、Git 提交和推送；未执行 Git 写入，任务保留当前实现与验证材料供后续交接，不伪造已推送／已关闭状态。
