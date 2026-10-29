# Path文件工作流真实场景设计

> 状态说明：本文保留设计阶段记录，实际验证与准入以[本项目准入记录](path-admission.json)为准。

## 来源、许可和入口

固定 `jaraco/path@b5ae11e41ba64a9e27fdc42d8c138d7db7699910`，完整32个Git跟踪文件。按上游AGENTS要求已获取并完整读取 https://blog.jaraco.com/skeleton/ 。原版pyproject声明MIT，许可证由coherent.licensed构建生成，保留固定提交真实构建许可于seed/app/licenses/LICENSE.path.build.txt，原占位版权行不替换，来源与分发元数据SHA见path-generated-artifact.json。原版Git树不添加假LICENSE。

已读in_place完整实现、原生对应测试、walk/walkfiles/glob、write_text/write_bytes/chunks以及merge_tree真实签名。当前镜像143主项（142通过／1上游Windows跳过），包含27模块doctest；新原生校准证据与私有runner版本分别固定。

## 四场景九项任务

| 场景 | 任务 | 业务问题和合法结果 | 验收边界 |
| --- | --- | --- | --- |
| PA-S01 文件格式保真 | PA-U01 理解 | write_text的默认换行归一化、linesep=None与指定分隔符 | 合成Unicode和混合换行的真实bytes，不泛化Windows结论 |
| PA-S01 | PA-C01 咨询 | 字节保真复制与文本转换如何选已有API | bytes/write_bytes或明确二进制chunks；不发明新函数 |
| PA-S02 目录资产盘点 | PA-U02 理解 | glob含**是否递归 | 当前glob不递归，对照真实多层目录walkfiles |
| PA-S02 | PA-C02 咨询 | 怎样跳过一个目录的整棵子树 | walk返回的生成器可send遍历谓词；正确处理send返回值，匹配过滤不同于剪枝 |
| PA-S03 目录内容合并 | PA-U03 理解 | merge_tree覆盖源同名文件并保留目标独有文件 | 合成源／目标字节和ignore规则，不当作删除同步 |
| PA-S03 | PA-C03 咨询 | 已有ignore/copy_function是否需要重造 | 用已有参数及明确复制策略；未知镜像删除语义另作业务选择，不实施删除 |
| PA-S04 取消时重写恢复 | PA-D01 诊断 | 取消后原文件异常，先取API、异常、生命周期和备份时序 | 披露合成复现后定位；材料不足正常收口 |
| PA-S04 | PA-P01 方案 | 界定用户块异常恢复和持久／原子文件保证 | 正常／RuntimeError已有事实，明确仅异常清理非崩溃原子协议 |
| PA-S04 | PA-M01 修改 | in_place取消／退出与自定义BaseException时恢复原字节、关闭流且原异常继续传播 | 单文件最小修复加真实公开测试，保留原接口和完整143节点 |

requires均为空，八项非修改。PA-M01仅授权library/path/__init__.py和library/tests/test_path.py。默认取消场景先诊断／方案再修改，并提供diagnose_only、unavailable和modify_direct入口；其他任务材料均自足，不以代码交接制造假依赖。

## 工程正反验收

原版in_place在用户块只捕获Exception，KeyboardInterrupt／SystemExit／GeneratorExit及自定义BaseException会穿过清理分支却在finally删除备份，既不恢复原字节也不关闭流。目标只扩展用户块异常清理：备份恢复、reader/writer关闭、同一异常对象继续传播。正常成功、RuntimeError、二进制和自定义backup_extension、权限及无遗留备份均须保持；不混入setup/open失败、断电原子性、fsync、跨设备或并发策略。

原版业务失败／最小参考通过／仅捕获常见内置异常的反例拒绝、两项公开参数化测试原版失败与参考通过、完整原生集合分别记录。不会在真实文件、真实HOME或生产目录执行重写；所有操作限制独立临时目录。
