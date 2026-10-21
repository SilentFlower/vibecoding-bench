# Python-decouple真实配置场景设计

> 状态说明：本文保留设计阶段记录，实际验证与准入以[本项目准入记录](python-decouple-admission.json)为准。

## 来源和边界

固定 `HBNetwork/python-decouple@0573e6f96637f08fb4cb85e0552f0622d36827d4`，完整30文件和MIT许可保留。已完整重读361行实际模块：Config.get先检查环境再查Repository，再用default并cast；RepositoryEnv在构造时读取文件；AutoConfig首次调用后保留Config；编码参数和任意callable cast已存在。目标镜像原生67项通过，离线mock依赖已冻结。

本仓九项真实业务任务均无需修改库。BOM可用已有encoding='utf-8-sig'，真正CSV语义可用已有callable cast，不把研究中提出的可选增强强制变成工程任务。没有工程目标，不编造原版缺陷修复或代码接受。

## 四场景九任务

| 场景 | 任务 | 用户问题与合法结果 | 实际程序事实 |
| --- | --- | --- | --- |
| DC-S01 启动配置 | DC-U01 理解 | 环境、文件、默认的顺序及空字符串 | 空环境值仍获胜；缺失且无默认才UndefinedValueError |
| DC-S01 | DC-C01 咨询 | bool/int/Choices转换失败是否回退 | bool按词表；非法int/choice传播ValueError，不自动回退 |
| DC-S01 | DC-P01 方案 | 启动时显式校验并一次发布配置 | 现有Config/Csv/Choices和应用层收集错误；不虚构内建schema或事务 |
| DC-S02 文件变化取证 | DC-D01 诊断 | 文件修改后值没变，先取读取时序和实例 | 真实披露RepositoryEnv构造后文件变化；不可提供可insufficient_information |
| DC-S02 | DC-C02 咨询 | 文件快照和动态环境的重载策略 | 旧Repository保留旧文件值，新建读取新值；环境每次读取，不承诺原子多键快照 |
| DC-S03 ENV读取 | DC-U02 理解 | 首BOM为何进入首键，如何用已有编码 | 默认UTF-8和utf-8-sig对照，值内U+FEFF保留 |
| DC-S03 | DC-C03 咨询 | ENV解析是否就是shell/dotenv通用语法 | export前缀是键的一部分，值内#和=保持；不执行或插值shell |
| DC-S04 列表配置 | DC-U03 理解 | Csv的shlex、引号、空项和后处理 | 真实#、反斜杠、连续逗号、引用逗号和tuple/int结果 |
| DC-S04 | DC-C04 咨询 | 需要真正CSV字段保真时是否必须改库 | 用已有自定义callable cast结合标准csv.reader保留空项/#/反斜杠 |

四场景九项，requires均为空。DC-D01初始不披露时序和根因，提供normal、diagnose_only、unavailable；后续C02公开完整独立复现。全部使用合成无敏感配置和专用临时目录，不读真实父目录或/run/secrets。

## 验收

八项原生程序事实和D01真实对话评审分别验证；完整原版67节点由冻结基线保留。默认和材料分支走真实产品链mock，所有任务只读且不应产生接受代码检查点。当前仅完成设计，不计正式准入，真实模型效果不由mock推断。
