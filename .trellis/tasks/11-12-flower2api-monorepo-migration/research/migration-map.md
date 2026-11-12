# 迁移盘点与目标映射

## 来源基线

- 当前父仓分支 flower2api；基线提交 `142ea0c0f35267f33cc0aa3a09eef4be10992bf7`。
- cc2api 子模块提交 `7cbf3e354e9e5570b4e323362c18e5133d913a3e`，本轮盘点时业务工作区干净。
- cc-runtime-bridge 源码提交 `7cfe8b3734111dae4758a7e2006f43e5f1cc71e9`，独立仓库的既有 dirty 属于任务、workspace及未跟踪产物。
- 实施前重新核对分支、来源SHA及实际 dirty。基线变化时按原映射重新核验。

## 源码映射

| 原路径/来源 | 目标 | 说明 |
| --- | --- | --- |
| cc2api/web | apps/web | Vue应用、配置、依赖锁及资源 |
| webui | apps/legacy-web | 原生JS工程页及独立环境样式 |
| cc2api，排除web | services/gateway | Rust源码、Cargo锁、第三方依赖及组件脚本 |
| orchestrator | services/orchestrator | Python模块、依赖及对应测试 |
| cc-runtime-bridge业务源码 | services/runtime | src、native、web、scripts、tests、依赖锁与组件文档 |
| project_library | resources/project-library | 工程种子与内容清单 |
| topics.md | resources/topics.md | 当前功能继续使用 |
| research/github-projects | resources/project-research | 程序读取的项目研究内容 |
| doc、docs及其它研究说明 | docs内对应主题 | 按实际消费关系归类，既有dirty文件保留原位 |
| images、deploy、scripts | 保留原职责 | 修复新源码入口与构建映射 |

运行时的业务源码与项目spec来源采用已提交快照；来源仓任务、日志、私有配置、缓存、artifacts和运行状态按原归属保留。记录原仓URL、提交、文件清单与摘要，避免将业务导入与工作区复制混为同一操作。

## Trellis映射

| 原spec分区 | 目标spec分区 |
| --- | --- |
| vibecoding-bench/backend | orchestrator/backend |
| vibecoding-bench/deploy | platform/deploy |
| vibecoding-bench/frontend | legacy-web/frontend |
| cc2api/backend、protocol、deploy | gateway对应层 |
| cc2api/frontend | web/frontend |
| 运行时/backend、frontend中的有效合同 | runtime对应层 |
| 运行时/operations中的项目专项规则 | platform/operations，保留原专项触发条件与来源 |
| 两边guides | 根guides，按节去重并保留独有内容 |

运行时backend的runtime-contract、logging-guidelines与frontend的state-management含实际合同。多个其它文件仍是待填写模板；实施时逐份核对内容后处理索引，模板留存来源清单。现有大spec先按归属迁移，独立合同及标题锚点完整保留。

## 具体引用边界

- deploy/v3/manage.py 的build当前读取子仓HEAD，精确冻结cc2api、orchestrator、webui、project_library及research/github-projects。
- deploy/v3/system_release.py 的data_contracts与component_content依赖现有相对路径，必须分别处理真实读取位置和对外逻辑身份。
- deploy/v3/install_system_updater.py 的SOURCE_FILES是宿主固定源码包清单，upgrade_system_updater使用同一清单进行精确校验。
- cc2api/src/handler/router.rs 的RustEmbed目录为web/dist；前端从crate目录迁出后需同步本地构建与Docker嵌入方式。
- orchestrator/main.py 的工程库/研究默认路径由自身位置派生，源码搬迁后需核对开发默认值及镜像内默认值。
- 已有349个dirty文件中包含旧spec引用与任务记录；采用旧入口转向或显式映射解决历史引用，当前任务使用新权威路径。

## 所有权证据

根仓flower/skill-garden锁定0.6.13-beta.12，.flower/state.json记录config.yaml的受管Patch。packages/default_package为项目映射配置，沿项目配置保留边界修改；受管codex模式及其它Patch保持原语义。spec为项目自有知识。根工作流、hooks、skills和runtime脚本沿现有Flower安装使用。
