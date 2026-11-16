# 目录迁移与规范整合实施计划

## 开工前

1. 复核根仓/两个来源仓HEAD、dirty、子模块、已有349个保留文件与Trellis所有权，保存精确基线。
2. 从research/spec-inventory.json开始读取对应完整spec和代码，输出逐文件来源/目标映射；新增未知来源单独记录。
3. 复核现有构建入口与CI结果，区分本地可验证范围和远端发布/安装范围。

## 阶段一：源码收编

- 按固定cc2api提交展开父仓直接跟踪源码，保留来源与第三方许可。
- 将运行时已提交业务源码及依赖锁纳入services/runtime；组件文档和局部测试完整保留。
- 统一来源记录与build的组件版本说明；先验证原转发及工程功能的构建路径。

## 阶段二：模块迁移

- 网关移入services/gateway；编排移入services/orchestrator。
- Vue应用移入apps/web；静态页移入apps/legacy-web。
- 修正本地命令、RustEmbed、Python根定位、精确构建快照与Docker输入。
- 更新固定宿主源码来源/目标映射、组件内容摘要逻辑及对应回归。

## 阶段三：资源和文档

- project_library→resources/project-library，topics.md→resources/topics.md，research/github-projects→resources/project-research。
- 检查所有运行时资料读取与白名单摘要，保持内容及许可。
- 按主题整合doc/docs/研究说明到docs，dirty文档保持原位并记录例外。

## 阶段四：Trellis整合

- 按映射逐模块迁移spec，完整保留有效合同，逐节核对公共指南。
- 重建准确index及package映射，验证Flower受管Patch语义和项目配置保留边界。
- 列出并处理历史spec/JSONL链接，旧引用使用明确转向，新增任务使用新路径。
- 迁移来源记录保留原仓、提交、原路径、目标、摘要及合并依据；历史任务和workspace沿原身份保存。

## 验证计划

- 新路径对应Rust `cargo fmt --check`、`cargo test`，Vue `npm ci`及`npm run build`，运行时Bun锁定安装、typecheck、unit/integration及原生消费者专项；按实际改动及原固定制品可用性运行对应测试。
- Python按新路径运行编排器与deploy/v3相关测试；`verify_database_definitions.py`核对迁移定义及登记不变，部署工具语法与三个工作流actionlint检查。
- 内容映射：源码/依赖锁/资源数量与SHA、许可、链接/权限、旧文件保留与受管配置边界。
- 根Trellis `get_context.py --mode packages`；gateway/runtime/orchestrator/web/legacy-web/platform代表查询；index和相对链接、任务JSONL及转向闭环检查。
- 宿主固定源码包在仓库外独立导入；旧v3合同/签名清单读取、双库兼容、内容身份及更新恢复回归。
- 使用独立验证目录执行同批镜像构建和离线升级/回退验收，合成账号及本地上游；实际生产发行/安装另外验收。
- 全部必要验证通过后进入Check-All，再按Spec和精确Git计划收尾。每阶段证据记录到本计划的完成项。

## 回退与范围

- 每阶段验证失败时保留已完成事实和映射，先修复当前迁移边界。
- 运行数据、源仓已有dirty与根仓349个文件按基线保护；借助源码映射定位回退点。
- 目录搬迁不包含功能退役或协议改写，品牌/页面设计由后续任务处理。

## 实施进度

- 已领取并完成首次 Brief 开工回执，任务处于 in_progress，按 inline 路由实施。
- 三组件源码已收编并迁入 apps/services；工程、题库及研究资料已迁入 resources；文档按主题归位，原编辑中文档保持原位。
- `deploy/v3/source_layout.py` 提供来源到旧 v3 逻辑路径的映射。构建、迁移定义核验、固定宿主复制和验证工具已接入；部署目标路径保持原合同。
- 55 份规范来源与逐文件摘要已保存，9 份模板归档，公共指南按节合并，六个 package 与十个规范索引已建立。新旧任务引用均有解析入口。
- Rust、Vue、运行时类型检查/180项单测、部署154项回归已通过。全量 Python、原生集成及同批镜像验收继续收口。
- 两项来源仓原有测试失配已复现并调整夹具：环境表补足必填字段；根 env 清理沿现有合同，拒绝测试改用 workdir。
- 工程库 37,625 个文件摘要核对通过，100项目/600目标结构校验通过。原始343项工作区内容核对一致。

### 定向回归收口

- Python 服务用例清单共1,238项，合并全量前段与末组37项的结果覆盖全部测试；1项沿原条件跳过。两项旧库夹具已在原提交快照复现并按实际基线字段补齐。
- 运行时集成48项通过；常驻池长序列场景有一次20秒超时，独立无外网复验通过。原有env拒绝夹具按已生效合同改为workdir拒绝。
- 管理浏览器矩阵通过：两个时区、明暗主题、1280/390宽度，真实模型请求为0。旧说明断言同步为现有界面原文。
- 全部Python语法、三个工作流actionlint、Shell/原生JS语法、Compose配置和网关Docker静态检查通过。
- 155处受管框架内容与来源一致；两库定义/登记字节一致；原始343项工作区摘要一致。
- 最终镜像批次为flower2api-layout-verified-20261112，固定beta.5运行时摘要继续核验；离线升级验收使用该精确清单。

### 联合验收完成

- 最终批次的14项真实Docker离线场景全部通过，真实模型调用为0；覆盖v1→v2更新底座、双库迁移、原三角色复用、按需重建、停止状态保留、显式回退、双库和进程中断恢复，以及精确镜像保留/回收。脱敏结果见research/upgrade-verification.json。
- 候选Git索引包含44,980个文件，三组件源码与锁文件完整，gitlink为0。迁出/迁入路径均已登记。

### Check-All 修复与重检

- CHK-001：根 `.gitattributes` 两条工程库规则同步到 `resources/project-library`，保留冻结文件的原始换行与验证补丁上下文。
- 在隔离候选索引重建受影响资源后，37,625 个 Git blob 与模式逐项匹配原 v3 来源，586 处潜在 CRLF 归一化已消除。
- 从候选索引检出全新副本，按正式 v3 构建快照布局调用既有 `restore_upstream_checkout_bytes`，仅恢复两处已登记 python-dateutil 上游检出转换。100项目/600目标验证通过，工程库摘要与迁移前一致。
- 新增实际 Git 入库回归：显式 `core.autocrlf=input` 下 CRLF 字节保留，验证补丁空白上下文通过检查。该用例已纳入 CI 现有 `test_system_workflow` 发现范围。
- 部署回归155项全部通过，35.215秒；本轮两处实际修复文件的 diff 空白检查通过。逐项 Git 对象与全新检出证据见 `research/resource-git-validation.json`。
- 重检结论为通过；平台在线更新权威规范已补充源码映射、固定宿主包及 Git 冻结资源合同，规范外变更指纹一致，索引/链接与空白检查通过。
