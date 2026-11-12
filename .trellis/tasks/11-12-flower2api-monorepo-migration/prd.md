# Flower2API 目录迁移与 Trellis 规范整合

## Goal

将三项目纳入一个按职责组织的源码仓库，并使 Trellis 项目知识与新结构一致，支持现有 v3 持续原地升级。

## Background

- 用户已确认统一源码仓库，以及 apps/web、apps/legacy-web、services/gateway、services/orchestrator、services/runtime、images、deploy、resources、docs、scripts 的目标结构。
- 用户明确要求同步合并 .trellis 中的 spec 等内容。
- 用户要求按小步迁移，沿原 v3 部署升级；品牌/UI 和功能精简由后续事项处理。
- 当前父仓已有36份 spec，运行时仓库有19份 spec；清单与SHA见 research/spec-inventory.json。cc2api 的项目规范已位于父仓。
- 工作分支 flower2api，来源 v3；此任务属于 ../11-12-flower2api-unification。

## Requirements

- R1：cc2api 由父仓直接管理源码；cc-runtime-bridge 的明确已提交源码纳入同一仓库。保留来源提交、必要许可及第三方代码，原有独立仓库工作内容保持归属。
- R2：网关、编排器和运行时分别归入 services/gateway、services/orchestrator、services/runtime；Vue后台归入 apps/web，现有静态工程页归入 apps/legacy-web。各模块保留依赖锁和职责。
- R3：工程库、题库及程序依赖研究资料归入 resources；项目文档归入 docs，仓库级命令归入 scripts，现有 images/deploy 职责保持明确。
- R4：统一根目录 Trellis。spec 按新模块分区，公共指南去重，跨模块合同保留一个权威位置。每个原有效合同均有迁移去向与来源，模块专属规则按实际技术栈保持。
- R5：package 映射、spec 索引与链接、当前任务上下文和源码引用同步更新；已有任务引用继续有可解析入口，历史任务/日志与源提交可追溯。
- R6：v3 的现有账号、环境身份、凭据、HOME、工作区、项目成果和历史记录沿原数据根保留；既有更新信任根、镜像/发行身份与数据库合同保持兼容。
- R7：每一步迁移具备文件映射、内容核验和定向回归；最终从当前仓库完成构建与验证，步骤之间可以独立复核和定位回退点。

## Constraints

- 既有349个工作区改动文件按原归属保留，当前运行时仓库的任务/日志与未跟踪产物按来源保护。
- 导入源码及规范采用明确的已提交来源；原仓未提交的业务改动若出现在目标范围，先列为待合并事项。
- Trellis 的项目规范与 package 配置可按所属项目调整；Flower 管理的工作流、脚本、hooks与skills沿插件所有权规则维护。
- 历史记录保留原任务身份和来源链接；当前运行状态继续由本仓管理。
- 本轮保留现有产品功能和运行时私有协议。

## Acceptance Criteria

- [x] 单次克隆当前仓库可取得三组件项目源码及依赖锁，cc2api 的 gitlink 已被源码管理替代。
- [x] 目标目录均存在，构建、开发与验证入口按实际新位置工作。
- [x] 工程库、题库与研究资料的数量及内容摘要对应迁移映射，原用户数据路径保持兼容。
- [x] 所有有效 spec 合同具备明确去向；公共指南完成有依据的去重，原技术栈规则和行为要求完整保留。
- [x] get_context --mode packages 展示新模块；代表性 spec_router 查询命中正确新入口；索引/相对链接/任务JSONL引用检查通过。
- [x] 已有任务、日志和基线文件按原归属保留；来源追溯可以定位旧仓、旧提交和原spec路径。
- [x] Rust、Vue、Python和运行时的对应构建及回归通过；同批镜像、固定更新源码包与旧v3发行兼容验证通过。
- [x] 原 v3 升级合同通过离线回归，发布与生产安装继续由后续明确动作验收。

## Non-Goals

- Logo、UI风格和页面功能重构；功能删除。
- 新建生产部署、迁移生产账号数据、正式发布与线上安装。
- 修改 Trellis/Flower 的公共工作流语义。
