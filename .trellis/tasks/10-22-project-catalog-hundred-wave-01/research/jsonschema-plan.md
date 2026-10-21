# JSON Schema独立业务任务计划

> 状态说明：本文保留设计阶段记录，实际验证与准入以[本项目准入记录](jsonschema-admission.json)为准。

固定`c497561ea0a95f5aac09cd63d15eb1420eb7bbec`，完整627个Git条目与COPYING保留。`json/tests/latest`的原Git链接blob按普通文本保存，模式差异在source-proof逐项注明；各draft的完整原生语料不经过此别名。开发分发版本来自该检出的真实历史构建元数据，不冒称发行版4.x。

已读validators.py的create／check_schema／iter_errors／validate／extend、_types.py、_format.py、exceptions.py，以及固定referencing wheel的Resource／Registry定义。任务覆盖五种实际交付：配置校验和错误清单、格式取证和实例局部格式器、进程内Decimal兼容方案、组合schema的闭合属性、离线引用注册表。

九个独立任务全部只读，默认requires为空。JV-D01只在拿到真实schema和调用后判断format漏校验；材料不可得可正常结束。default不负责填充值、未知format不自动拒绝、bool不等于integer、additionalProperties不跨allOf分支合并属性，均有正常／反例。Decimal扩展是已有API的应用方案，不虚构库缺陷。离线引用只准入合成urn注册资源；未知资源失败，不测试真实网络。

当前镜像完整原生8529项：8297通过／232上游skip。首轮唯一失败来自本轮私有metadata缺少原pyproject明确声明的MIT License-Expression；补真实元数据后第二轮完整通过，原失败留存。没有删除test_license或安装另一份jsonschema。逐任务业务、协议模拟和交付尚待实际运行，不以原生基线替代准入。
