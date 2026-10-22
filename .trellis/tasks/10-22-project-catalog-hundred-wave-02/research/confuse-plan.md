# Confuse场景任务表

固定提交bf42783301ac4e9c640328ec95486952fd599ce6，MIT，完整47个Git文件。已读ConfigView／RootView／Configuration的来源、get／flatten、redaction、set_file／set_env／reload，YamlSource／EnvSource的完整load及Integer／Template转换。当前镜像299主项通过、1个缺少可选Sphinx的发行工具模块收集跳过，JUnit300；跳过不算主项。

| 任务 | 独立业务价值和当前事实 | 授权与验证 |
| --- | --- | --- |
| CF-U01 理解 | raw mapping、子键回落与flatten不是同一个投影 | 完整合成层级；只读；host覆盖、port回落及完整形状 |
| CF-C01 咨询 | Integer不是严格整数解析／范围校验器 | float、string、bool实际控制；只读；建议显式类型政策 |
| CF-U02 理解 | 环境覆盖的解析、嵌套与快照时点 | 清空后的合成环境；只读；文件reload不刷新EnvSource |
| CF-C02 咨询 | 脱敏仅影响所选输出投影 | 合成PUBLIC_SAMPLE；只读；原值和普通flatten仍可访问 |
| CF-D01 诊断 | 数字外观不等于实际整数类型 | 按请求披露源／类型／模板，缺材料正常收口 |
| CF-P01 方案 | 多源重载失败可能已更新前一来源 | 两个临时文件；只读；计划独立验证后一次发布，非事务声明 |
| CF-M01 修改 | 成功重载必须移除该文件源已删的键 | 仅sources.py与公开测试；保留对象／元数据、空源、可选缺失和失败前值；正反与完整原生另验 |

五场景七任务，没有虚假answer／code依赖。修改仅约束单YamlSource成功替换，不扩张为环境刷新或跨文件回滚。当前内容经实际schema2和离线制品校验后仍须业务、产品链、页面／API／数据库及正式交付证据；以后续同名admission JSON为准。
