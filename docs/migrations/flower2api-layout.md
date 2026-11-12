# flower2api 单仓目录

## 模块与命令

| 目录 | 职责 | 仓库根验证入口 |
| --- | --- | --- |
| `apps/web` | Vue 管理后台 | `npm --prefix apps/web ci && npm --prefix apps/web run build` |
| `apps/legacy-web` | 工程与账号静态页面 | `node --check apps/legacy-web/app.js` |
| `services/gateway` | Rust 网关、账号池与存储 | `cd services/gateway && cargo test --locked` |
| `services/orchestrator` | Python 编排与工程执行 | `PYTHONPATH=services/orchestrator:deploy/flower2api .venv/bin/python -m unittest discover -s services/orchestrator` |
| `services/runtime` | 原生内核适配及本地诊断 | `cd services/runtime && bun install --frozen-lockfile && bun run typecheck && bun test tests/unit` |
| `resources` | 工程种子、题库和程序读取的研究资料 | `python3 scripts/validate-project-library.py` |
| `images` | 镜像定义及角色脚本 | 由 v3 联合构建生成两镜像 |
| `deploy` | 构建、发行和原地升级 | `python3 deploy/flower2api/manage.py build --release <唯一批次> --manifest <新清单>` |
| `docs` | 项目说明和研究文档 | 本文件及来源清单 |
| `scripts` | 仓库级验证和开发工具 | 按各脚本 `--help` 选择入口 |

## 升级兼容

源码位置通过 `deploy/flower2api/source_layout.py` 映射为稳定逻辑路径。构建快照继续生成 v3 所需结构；镜像内 `/app`、`/webui`、`/repo` 和原数据挂载沿现有合同。

宿主更新器沿用固定安装文件路径 `source/deploy/v3/`。安装与升级工具从 `deploy/flower2api/` 读取源码，复制到原宿主包结构；`source_layout.py` 也随固定清单分发。部署目录独立识别，兼容上一版使用 `services/` 与 `deploy/v3/` 的单仓。新部署目录存在时，缺失文件保持可见。旧发行和旧布局夹具继续可读。目录搬迁保持数据库定义与登记文件的原字节。

根 `.github/workflows/` 统一维护构建与手动发布。网关导入的两份旧工作流已移除，原来源和版权记录继续保留。日常脚本为 `scripts/flower2api-stack`，旧 `scripts/v3-stack` 兼容转发。

新联合清单的两个 revision 均指向统一仓库提交。导入前的独立组件版本与固定执行制品见 [来源记录](./flower2api-sources.json)。运行时源码导入与执行制品升级分别验收。

## Trellis 知识整合

当前开发统一使用根 `.trellis/`。package 为 `platform`、`gateway`、`orchestrator`、`runtime`、`web`、`legacy-web`。共享指南位于 `spec/guides`。

原 spec 去向、摘要、合并动作和来源标题见 [规范映射](../../.trellis/tasks/11-12-flower2api-monorepo-migration/research/spec-map.json)。原始 55 份文件存入同任务的 `research/spec-originals.tar.gz`。有效正文按模块维护；旧父仓 spec 路径保留转向入口，历史任务继续使用原身份。

公共指南合并同名主题并保留独有章节。模板占位文件收进原始来源包。运行时专项恢复规则保留原仓工具的适用条件。

原仓的任务、日志、私有配置和本地运行状态按来源保留。正在编辑的 `doc/claude-code-2.1.303-protocol-study.md` 原位保留，其内容归属后续合并。
