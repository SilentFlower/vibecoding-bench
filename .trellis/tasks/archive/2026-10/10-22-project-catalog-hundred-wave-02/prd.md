# 百项目扩容第2阶段：30项目真实场景内容包

## Goal

将本阶段固定清单中的三十个研究项目全部转为与现有十项目同标准的正式真实场景内容包，作为剩余九十仓全量接入目标的第2阶段。

## Background

- 母任务 `../10-22-project-catalog-hundred/` 覆盖全部剩余九十仓；用户要求auto-loop推进，并反馈二十三个子任务过多，因此采用三个阶段任务，阶段内部小批执行。
- 当前最初基线为10项目／45场景／107任务、版本 `real-project-scenarios-v4-en`。前序阶段都通过时，本阶段完成后的累计方向为70项目；实际数始终以当前已准入目录为准。
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
| alive-progress | `69d9bf0aba6276e2434a3a595cceca55040d64d7` | `https://github.com/rsalmei/alive-progress` |
| jmespath | `2812594e69d43098ef60f81f4efc404c071b0418` | `https://github.com/jmespath/jmespath.py` |
| confuse | `bf42783301ac4e9c640328ec95486952fd599ce6` | `https://github.com/beetbox/confuse` |
| simplejson | `9950b7e5f4443fff8defb51e80e41ab40d0a36b9` | `https://github.com/simplejson/simplejson` |
| marshmallow | `b762ea2d59ca52fe5df76b90de14bed7e5ec5607` | `https://github.com/marshmallow-code/marshmallow` |
| inflect | `99596854bd296af1557db2015cfa98c8104ec155` | `https://github.com/jaraco/inflect` |
| tqdm | `9cf5a12b1f955468a17f0ba3c59092b23e4258ac` | `https://github.com/tqdm/tqdm` |
| pyyaml | `f5e4504a92f169f65350a1047dccb23bc97028be` | `https://github.com/yaml/pyyaml` |
| pluggy | `0224f79fc75efadaafe24dbab9deee2ff616ecd7` | `https://github.com/pytest-dev/pluggy` |
| xlsxwriter | `5d4606d89a955226d2d0825a0f44309043ae7251` | `https://github.com/jmcnamara/XlsxWriter` |
| mistletoe | `ebf9ae4e9279f3d8c79b7cf2710f7e73ea6438a7` | `https://github.com/miyuchina/mistletoe` |
| python-docx | `e45454602b53e8e572b179ccf1c91093ec9f4ed7` | `https://github.com/python-openxml/python-docx` |
| python-pptx | `278b47b1dedd5b46ee84c286e77cdfb0bf4594be` | `https://github.com/scanny/python-pptx` |
| mdit-py-plugins | `519953da0a394a92534bc27580f4e7415462df44` | `https://github.com/executablebooks/mdit-py-plugins` |
| dynaconf | `32f38478350a80020e7aab60a3cbd29dd7f8d9ea` | `https://github.com/dynaconf/dynaconf` |
| attrs | `ee66e7274852438cc23d4240a1a9cd632fda8b52` | `https://github.com/python-attrs/attrs` |
| cssselect | `3069b6da75e1adf27939ca541dcc9fb9b961abc6` | `https://github.com/scrapy/cssselect` |
| structlog | `19c4f21059e853114efa7a93b6e675d93bf7934e` | `https://github.com/hynek/structlog` |
| cattrs | `57333a234a19903a94e5b181bc0aee6b187ee05c` | `https://github.com/python-attrs/cattrs` |
| flask | `d086db856be187255b8ec61ef409357393020f32` | `https://github.com/pallets/flask` |
| babel | `e2a17919f0eb988bfea2883b00793ca4d5d37c4f` | `https://github.com/python-babel/babel` |
| anytree | `2e0a1b956172654d75aff93277ce3d883355e0bf` | `https://github.com/c0fec0de/anytree` |
| werkzeug | `665e760ca6325a348ce03e5cf780b17e4be01848` | `https://github.com/pallets/werkzeug` |
| html2text | `5cf85510a2498546d5b48ad1bf7d75b146aac591` | `https://github.com/Alir3z4/html2text` |
| packaging | `1a62a26afe0f4881593e31bed4f7753bd1c8fe27` | `https://github.com/pypa/packaging` |
| bibtexparser | `af329ca482b29691caff69cb2f8e6099670a105f` | `https://github.com/sciunto-org/python-bibtexparser` |
| treelib | `83b3b87eaa7c56c9c7b86d19b2eede5252a1b482` | `https://github.com/caesar0301/treelib` |
| sqlparse | `60cdc649726bf1bc4f1b336050560b336da715ec` | `https://github.com/andialbrecht/sqlparse` |
| python-dateutil | `68994217fbe253835989e7c1e3eeef5c653088d1` | `https://github.com/dateutil/dateutil` |
| ftfy | `74dd0452b48286a3770013b3a02755313bd5575e` | `https://github.com/rspeer/python-ftfy` |

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
