# AGY系统提示词同形体实施计划

## 开工前提

- [x] 用户确认按AGY账号独立开关、默认关闭及固定映射范围。
- [x] 已读现有Account、AgySubmission、原生输入与账号控件，核对真实字段和调用。
- [x] 26字符参考表及幂等性质已记录。
- [x] 固定原版本地TLS完成系统文本零外部调用基线。
- [x] 三件套收敛、完整Brief评审通过后启动任务。

## 实施顺序

1. 建立单一规则JSON资源、版本身份和纯系统文本转换；补齐原样、开启、幂等、Unicode、多Part及大文本边界。资源纳入构建及身份验证。
2. 定义受信私有策略快照，接通Gemini账号准入、认证恢复、runtime_transport、Rust监督适配及Python严格校验。核对所有AgySubmission字面量和合成信封夹具。
3. 在独立system到Cortex自定义系统段之间应用转换，原始gemini_body与工具历史保持；保留worker复用、原许可与截止。
4. 实现实际处理回执与最小诊断字段，保存原始入站/实际提交视图来源，覆盖关闭采集、错误及不兼容规则。
5. 复用账号设置控件并更新提示，核对两账号保存和切换、迟到回执、桌面/390px草稿与焦点。
6. 跑真实网关/SQLite及固定原版本地TLS对照，补齐普通/SSE、工具、同请求认证恢复快照、后续请求开关变化、幂等、大文本和usage/cache保真。
7. 完成Check-All、Spec评估和精确Push计划；向请求记录子任务交接事件字段及视图来源。

## 预计影响

- gateway：service/agy_contract、gemini、runtime_transport、agy_runtime及对应测试；公开Gemini正文继续原合同。
- orchestrator：agy_runtime策略模块、规则资源、构建身份、输入解码、内核与监督协议及测试。
- web：Accounts.vue既有设置提示及账号浏览器验收。
- deploy：合成HTTP/SQLite、原生TLS及账号UI验证入口，必要源码布局和兼容断言。
- task：当前三件套、Brief和来源研究；其他任务记录按既有归属保留。

## 验证计划

| 范围 | 核心断言 |
| --- | --- |
| 纯转换 | 26字符逐项一致、码点数量、T(T(s))=T(s)、空/Unicode/大文本 |
| 字段边界 | 仅独立system变化；原始Gemini、用户、历史、工具和签名对照 |
| 策略合同 | 缺省关闭、严格布尔/版本、公共覆盖拒绝、旧执行端启用失败关闭 |
| 时序 | 账号隔离、HTTP冻结、认证恢复复用、工具下一HTTP再冻结、暖worker复用 |
| 实际出站 | 固定原版Cortex提交与本地TLS请求对应，普通/SSE一致 |
| 记录与用量 | 冻结/实际来源区分、开关与changed区分、采集关闭、源usage/cache字段 |
| UI | 两账号、CC、默认关闭、保存、草稿、焦点、迟到回执、390px |
| 交付 | 规则资源随包、无外部目录依赖、镜像资源构建及内容身份 |

基线探针为.trellis/.runtime/agy-homoglyph-baseline-probe.py，完整摘要在research/native-system-baseline.json。实施时将需要长期保留的验收纳入deploy/flower2api现有探针或新增明确入口。

按实际变更执行下列命令并保存gitignored日志；有效且未变化的既有完整回归可复用：

```bash
cargo fmt --check --manifest-path services/gateway/Cargo.toml
cargo test --locked --manifest-path services/gateway/Cargo.toml
PYTHONPATH=services/orchestrator:deploy/flower2api /root/project/vibecoding-bench/.venv/bin/python -m unittest test_agy_runtime test_agy_supervisor
npm --prefix apps/web run build
```

原生及浏览器探针使用明确任务镜像、合成凭据和隔离后台。真实Google生成预算0。缓存/计费效果保留独立外部验收；原生合成usage只验证来源保真。仓库既有python-dateutil种子摘要异常与本任务定向结果分别记录。

## 回退与收尾

关闭账号开关影响后续HTTP请求，原在途和工具结果按原策略完成。部署回退遵循当前凭据、身份及活动门禁，生产操作单独授权。首次Brief批准后实现细节变化按增量同步，范围或产品变化再交用户决定。
