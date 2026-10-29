# 百项目扩容第3阶段：30项目真实场景内容包

## Goal

将本阶段固定清单中的三十个研究项目全部转为与现有十项目同标准的正式真实场景内容包，作为剩余九十仓全量接入目标的第3阶段。

## Background

- 母任务 `../10-22-project-catalog-hundred/` 覆盖全部剩余九十仓；用户要求auto-loop推进，并反馈二十三个子任务过多，因此采用三个阶段任务，阶段内部小批执行。
- 当前最初基线为10项目／45场景／107任务、版本 `real-project-scenarios-v4-en`。前序阶段都通过时，本阶段完成后的累计方向为100项目；实际数始终以当前已准入目录为准。
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
| pypika | `465fb9ae12f7727d28785d087b64e6226da5714e` | `https://github.com/kayak/pypika` |
| arrow | `2224255c4acc594d734cef0bbc83360452a67983` | `https://github.com/arrow-py/arrow` |
| charset-normalizer | `0a9201767e9d888b5a5ed7ca44400192474ad1b0` | `https://github.com/jawah/charset_normalizer` |
| injector | `5daed12510fafc0bf73b6ef18d2884f78cd5e210` | `https://github.com/python-injector/injector` |
| loguru | `bce5dfd3b435b1d1658507d7e095ad7a9919bf1c` | `https://github.com/Delgan/loguru` |
| pyparsing | `810199f89bf916590426e1c5cb3d612584f11a2f` | `https://github.com/pyparsing/pyparsing` |
| markdownify | `bc98c9e134ec55b2853716ab859754f061cb7054` | `https://github.com/matthewwithanm/python-markdownify` |
| pyrsistent | `0c0b7aec8cd25b1d2d8ba07b10acdefd0f38f2c7` | `https://github.com/tobgu/pyrsistent` |
| feedgen | `97260abb1793eb164c458c10b493690beb413f6d` | `https://github.com/lkiesow/python-feedgen` |
| sortedcontainers | `3ac358631f58c1347f1d6d2d92784117db0f38ed` | `https://github.com/grantjenks/python-sortedcontainers` |
| wtforms | `af18fd6a7595d374aa707ff97b73df0dcc462ec2` | `https://github.com/pallets-eco/wtforms` |
| python-constraint | `d91ba03d1fd6acc30d64fd9d513dc0523f697b5b` | `https://github.com/python-constraint/python-constraint` |
| feedparser | `a22c5521cbb109871f1a2318948581901bd47e26` | `https://github.com/kurtmckee/feedparser` |
| portion | `622e7ca1f3a36a7cb337e6f51abeef0ee5e40c44` | `https://github.com/AlexandreDecan/portion` |
| textdistance | `d6a68d61088a40eef5c88191ccf79323dbf34850` | `https://github.com/life4/textdistance` |
| humanize | `785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b` | `https://github.com/python-humanize/humanize` |
| bidict | `299fedc89f1d70d5d41cf7922564b376d3e2d435` | `https://github.com/jab/bidict` |
| tablib | `966876c76a6378557c1951badc1665b4d1375875` | `https://github.com/jazzband/tablib` |
| chardet | `fa905b359cbcaba93a35fd6429ba9ec4b156c1c1` | `https://github.com/chardet/chardet` |
| natsort | `e9a3a2a307580a1f2be8c57bba50fba45789ada0` | `https://github.com/SethMMorton/natsort` |
| transitions | `bd42b38f3627e6bca7274fb4d9af2e105f75da7c` | `https://github.com/pytransitions/transitions` |
| html5lib | `fd4f032bc090d44fb11a84b352dad7cbee0a4745` | `https://github.com/html5lib/html5lib-python` |
| pendulum | `e06dacedc4cdea90fa1286b3965d180ab94cf251` | `https://github.com/python-pendulum/pendulum` |
| python-liquid | `878f589adff6cb6bf08ccea7895570f96980248e` | `https://github.com/jg-rp/liquid` |
| python-statemachine | `ec5d8173f740b37941818df13727db9d64ef498d` | `https://github.com/fgmacedo/python-statemachine` |
| webcolors | `6c8da6832eb4ae2591a1883a0d1371263d6cd4db` | `https://github.com/ubernostrum/webcolors` |
| wrapt | `6b4e844950213118b19e613248d2bc9469eb731e` | `https://github.com/GrahamDumpleton/wrapt` |
| funcy | `e8febffd57f80db8ca3a55fb1edd0feee2290d61` | `https://github.com/Suor/funcy` |
| collective-icalendar | `3ecf079acba0e592ea6a40c456514984c8657852` | `https://github.com/collective/icalendar` |
| sqlglot | `67961afbed7c986dfe26ab82db89a25814c1bdcb` | `https://github.com/tobymao/sqlglot` |

## 用户确认的源码范围

- 用户确认保留SQLGlot上述固定公开主仓，交付其完整公开源码、公开测试及许可；原三十仓和一百仓项目集合不替换。
- 可选私有外部集成测试 `sqlglot-integration-tests@8cbf013a7b0bd1871abce4ebb543560d0e554799` 明确未验证，仅保存Gitlink身份和原始不可取得证据，不将其内容、许可或测试计为已交付／通过。确认原件见 `research/sqlglot-public-source-scope.json`。
- R1／R4据此核公开主仓完整性和全部适用公开测试，其他仓仍保持原完整来源和准入要求。

## Acceptance Criteria

- [x] AC1（R1、R8）：本阶段三十仓逐项有实际来源、许可、完整源码和准入报告，正式目录实际新增全部三十个唯一项目，没有被遗漏或换成其他仓。
- [x] AC2（R2、R3、R6）：逐仓真实场景任务表、可达入口／分支、材料、合法结论、授权和独立正反验收齐全，实际任务数可重算，无模板凑数或隐藏材料泄露。
- [x] AC3（R4）：当前镜像离线业务及完整适用回归通过，实际候选绑定、工程原版／参考／错误候选证据可复跑，主项、子项、skip与资源逐项对账。
- [x] AC4（R5）：全部新增默认与必要分支通过真实产品链模拟，UI／API／数据库与材料消费、角色、尝试、接受代码及用量一致，mock不冒充真实模型效果。
- [x] AC5（R7）：此前内容字节、ID和历史读取保持，Git／Docker完整交付摘要及权限一致，失败记录保留、临时资源清理。

## Non-Goals

- 不强制每仓二十项，不直接实现所有旧研究路线，不以内部小批新增Trellis任务。
- 不重写调度、评审、UI和数据库，不增加账号配额，不静默改变当前公开平台合同。
- 本次auto-loop允许精确本地提交；不push、merge、发布镜像或部署，不调用真实模型／OAuth，不读取真实账号、配置或生产数据。
