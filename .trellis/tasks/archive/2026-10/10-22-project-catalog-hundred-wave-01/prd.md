# 百项目扩容第1阶段：30项目真实场景内容包

## Goal

将本阶段固定清单中的三十个研究项目全部转为与现有十项目同标准的正式真实场景内容包，作为剩余九十仓全量接入目标的第1阶段。

## Background

- 母任务 `../10-22-project-catalog-hundred/` 覆盖全部剩余九十仓；用户要求auto-loop推进，并反馈二十三个子任务过多，因此采用三个阶段任务，阶段内部小批执行。
- 当前最初基线为10项目／45场景／107任务、版本 `real-project-scenarios-v4-en`。前序阶段都通过时，本阶段完成后的累计方向为40项目；实际数始终以当前已准入目录为准。
- 历史研究与实际原生准入分开。本阶段固定来源和历史证据在 `research/source-index.json`，任务内部顺序在 `research/execution-batches.md`。

## Requirements

- R1：完整覆盖下表三十个独立仓库，保留固定源码、许可和完整提交；不得替换困难项目、生成同构样板或以安装库冒充候选。
- R2：围绕各仓真实业务制作多场景、可变数量的独立任务，按需要覆盖理解、咨询、诊断、方案及明确授权的修改。整阶段非修改任务多于修改，允许无需改代码、兼容方案和材料不足正常收口。
- R3：逐任务明确用户问题、当前行为、公开／披露材料、合法结果、授权、正常／反例和真实answer／code依赖；追问、测试、文档及重试不重复计数，旧二十步研究只作候选。
- R4：在当前目标镜像实际核源码与许可、原生入口、精确离线依赖、完整适用原生集合和资源。每项工程目标有原版失败、参考通过、错误候选拒绝及累计回归，主项／子项／skip分别对账。
- R5：全部新增默认与影响材料或业务结果的分支通过真实Scheduler／driver／独立评审／native verifier的隔离mock链，页面／API／数据库与角色、尝试、代码接受、预算、用量一致。
- R6：模型指令与私有评审英文，页面展示中文，原始代码／错误／业务字面保真。参考和私有rubric不进入候选，只读结果不产生代码检查点。
- R7：新增目录版本仅注册实际准入项目，全部此前就绪内容、环境、稳定ID与历史读取保持。Git导出与正式Docker交付完整文件、权限、SHA一致。
- R8：每仓保存任务表、准入和模拟证据；本阶段三十仓全部通过才能完成。受阻仓保留未完成，不用局部成功替代全量目标；母任务最终汇总全部阶段。

## Fixed Project Scope

| 项目 | 固定完整提交 | 研究来源 |
| --- | --- | --- |
| cachetools | `6f23e2a7b75a42d30cb9d890ab3ca4059ee01bfd` | `https://github.com/tkem/cachetools` |
| xmltodict | `6e29fba282e68631034dd2722a413b4e35276584` | `https://github.com/martinblech/xmltodict` |
| tabulate | `268615a5c27dc40e5c22454c07b44d5c50410da0` | `https://github.com/astanin/python-tabulate` |
| python-decouple | `0573e6f96637f08fb4cb85e0552f0622d36827d4` | `https://github.com/HBNetwork/python-decouple` |
| click | `2247b35ea1c47c727d7a06e51fa280e12a863ff6` | `https://github.com/pallets/click` |
| cli-helpers | `e2538b1d338ead4ed803ec0017017bf6779a380b` | `https://github.com/dbcli/cli_helpers` |
| mistune | `4bbaa04c391d650a2e1219781c9a9acd60571cce` | `https://github.com/lepture/mistune` |
| boltons | `4e5faa3d7e4008d89e0d8bf1ea87b6d9a061a16d` | `https://github.com/mahmoud/boltons` |
| more-itertools | `4aeb4338ae1407d8da9723e86da99efeb446f719` | `https://github.com/more-itertools/more-itertools` |
| configobj | `b7707c94c0317b8f89b704a01525a68eb6c72521` | `https://github.com/DiffSK/configobj` |
| dataset | `db592cc041014762bba55fd544e982170831f227` | `https://github.com/pudo/dataset` |
| python-markdown | `b41e0aaf1181f1a8cb200cf5a815aad7c0020d23` | `https://github.com/Python-Markdown/markdown` |
| markdown-it-py | `6f586542653a56d2ee8549a0dccfaa6ba5ebe14a` | `https://github.com/executablebooks/markdown-it-py` |
| path | `b5ae11e41ba64a9e27fdc42d8c138d7db7699910` | `https://github.com/jaraco/path` |
| petl | `cd5ed9dd3ec1c95eb4c2285bcc71d945f7acb86b` | `https://github.com/petl-developers/petl` |
| toolz | `451af60dec590a6010e2babdbf391ea8f815122f` | `https://github.com/pytoolz/toolz` |
| jsonschema | `c497561ea0a95f5aac09cd63d15eb1420eb7bbec` | `https://github.com/python-jsonschema/jsonschema` |
| docutils | `3577cb69446ed0c94c15f9b0836571d6d5c46882` | `https://github.com/live-clones/docutils` |
| agate | `202796ada63357c275a2a5f8685a983e37bad9bf` | `https://github.com/wireservice/agate` |
| csvkit | `6d19c625214977ab2988e674441ca24638bc12d3` | `https://github.com/wireservice/csvkit` |
| python-box | `a4c10e977b574114613431394b30412b50aaacce` | `https://github.com/cdgriffith/Box` |
| rich | `9d8f9a372cc5916fd4781fec207ced7ddac2f08f` | `https://github.com/Textualize/rich` |
| pydash | `ef6a6427e488e29e827e0e0819f2630ad3ff4cdc` | `https://github.com/dgilland/pydash` |
| configargparse | `3ab2f323abcdd321b6c423f9eb6304ce35681307` | `https://github.com/bw2/ConfigArgParse` |
| backoff | `d82b23c42d7a7e2402903e71e7a7f03014a00076` | `https://github.com/litl/backoff` |
| bottle | `8ec5fe29420d14998c0d86885083983eaea8b839` | `https://github.com/bottlepy/bottle` |
| deepdiff | `79e4379278b1cfdd8e9e3dccac364956908e8989` | `https://github.com/qlustered/deepdiff` |
| cerberus | `83f5dada76aa3179ef21b677a7f4235bf20c1566` | `https://github.com/pyeve/cerberus` |
| icecream | `05af3e95b0080162813bb017de90966bc75f3b91` | `https://github.com/gruns/icecream` |
| dpath | `15759d96a006fef5278de731cd263b4d839094c3` | `https://github.com/dpath-maintainers/dpath-python` |

## Acceptance Criteria

- [ ] AC1（R1、R8）：本阶段三十仓逐项有实际来源、许可、完整源码和准入报告，正式目录实际新增全部三十个唯一项目，没有被遗漏或换成其他仓。
- [ ] AC2（R2、R3、R6）：逐仓真实场景任务表、可达入口／分支、材料、合法结论、授权和独立正反验收齐全，实际任务数可重算，无模板凑数或隐藏材料泄露。
- [ ] AC3（R4）：当前镜像离线业务及完整适用回归通过，实际候选绑定、工程原版／参考／错误候选证据可复跑，主项、子项、skip与资源逐项对账。
- [ ] AC4（R5）：全部新增默认与必要分支通过真实产品链模拟，UI／API／数据库与材料消费、角色、尝试、接受代码及用量一致，mock不冒充真实模型效果。
- [ ] AC5（R7）：此前内容字节、ID和历史读取保持，Git／Docker完整交付摘要及权限一致，失败记录保留、临时资源清理。

## Non-Goals

- 不强制每仓二十项，不直接实现所有旧研究路线，不以内部小批新增Trellis任务。
- 不重写调度、评审、UI和数据库，不增加账号配额，不静默改变当前公开平台合同。
- 本次auto-loop允许精确本地提交；不push、merge、发布镜像或部署，不调用真实模型／OAuth，不读取真实账号、配置或生产数据。
