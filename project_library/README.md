# 真实项目场景内容库

当前正式清单采用内容 schema 2，包含三个固定版本的真实开源项目，共 13 个业务场景、20 个独立任务。任务覆盖理解、咨询、诊断、方案与明确授权的工程修改；每项目的数量由真实业务决定。

| 项目 | 场景 | 任务 | 工程目标 |
| --- | ---: | ---: | --- |
| python-frontmatter | 4 | 6 | 修复正文／handler 同名元数据的处理 |
| pydantic-settings | 5 | 7 | 修复嵌套字典 Union 环境变量解码 |
| Typer | 4 | 7 | 增强用户商品导出 CLI，库版本保持固定 |

共 17 个非工程任务与 3 个工程任务。固定入口可选择不同任务集合；补充材料、正常澄清、超时继续和修正均不增加任务数。100 个项目、约 600～800 个场景和约 2,000 个任务是后续内容池方向。

## 内容组织

- `catalog.json`：内容版本和就绪项目键。
- `projects/<key>/project.json`：固定来源／许可、场景入口、任务依赖、授权范围和验收引用。
- `projects/<key>/seed/`：场景初始库源码、应用和必要许可。
- `projects/<key>/materials/`：任务开放材料；`disclosure/` 为按冻结分支披露的补充材料。
- `projects/<key>/verification/`：控制端私有 rubric、业务验证、固定回归控制脚本及 contract。
- `environments/<id>/profile/profile.json` 与 `artifacts/`：固定 Python、资源档案、精确依赖和离线 wheel 摘要。

候选只获得固定源码、当前问题及应披露业务输入；隐藏参考、rubric 和评审包不进入候选工作区。通过问答只记录任务结果；工程任务通过授权范围、独立行为和适用原生回归后才接受代码检查点。

新内容使用执行策略 schema 3。正常回复先封存候选并严格释放，再进行程序验收和必要的同模型独立会话评审。评审复用原账号／模型与共享容量，私有 HOME、输入和日志独立；用量和预算单独记录。现有账号环境需要匹配评审资源布局后才能运行。

同模型以候选原生日志中实际使用的模型为准，评审固定使用该模型并再次核对。新任务从确定的已接受代码状态准备输入；上一任务未接受的改动另行封存，同一任务超时接续保留自己的半成品。Typer 应用增强除业务与原生回归外，还评审用户测试和用法说明。

## 本地校验与证据

从仓库根目录运行静态校验：

```bash
python3 scripts/validate-project-library.py
```

该命令检查内容结构、固定源码和离线制品摘要，并报告项目／场景／任务数量。它不调用模型，也不代表原生行为或运行链路已通过；新内容不使用旧 `--all` 参考运行时。

原生验证使用产品适配器，例如：

```bash
python3 scripts/validate-project-scenarios.py --project python-frontmatter --task FM-FX-01 \
  --image <本地账号镜像> --regression-only --output <证据.json>
```

去掉 `--regression-only` 执行业务验收；`--candidate` 指定候选根（包含 library/app），`--answer` 提供冻结回答，`--entry`／`--branch` 选择固定输入。原版故意不满足的修改目标可用 `--expect failed` 验证反例；`--with-regression` 要求业务通过后再跑完整原生回归。它不会调用模型。调度机制使用 `deploy/v3/run_local_verification.py --manifest <隔离清单> --project-scenarios-only --scenario-capacity 1`（另测容量 2）。分别记录目标镜像、命令、通过／跳过、资源和来源。当前保留了三仓原生回归校准材料；真实模型会话完成数仍为 0。内容制作、接入验证、本地模拟模型机制和真实模型成绩分别报告。

## 兼容与交付

旧 schema 1 内容、旧策略和已冻结发布按原版本读取；当前 catalog 不可用不应遮蔽历史批次与成果。旧 100 个生成项目、生成器和参考运行时保持退役；调度回归合成夹具只在测试临时目录生成，不计入真实项目规模。

内容按固定摘要注册到数据目录，离线环境与源码对象分开保存。新增内容与素材须同时通过 v3 Docker 上下文和源码快照规则核对；业务 `.env` 按冻结素材准备；Typer 上游自带的公开测试文件仅按精确路径与固定摘要保留，不放开其他环境文件。源码修改不代表已经发布、部署或删除历史数据。

项目运行规范见 [项目迭代规范](../.trellis/spec/vibecoding-bench/backend/project-iterations.md)，初始场景设计见 [三项目场景样板](../research/project-scenarios/README.md)。
