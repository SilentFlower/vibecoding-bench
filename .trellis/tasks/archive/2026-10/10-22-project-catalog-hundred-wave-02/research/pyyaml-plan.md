# PyYAML场景任务表

固定提交f5e4504a92f169f65350a1047dccb23bc97028be、MIT、完整642个Git文件。已读load／safe_load／all／compose／dump入口，Loader、Constructor映射与别名构造、Composer的单文档／别名规则、Node及错误mark定义和原生collector。当前目标镜像候选lib/yaml纯Python完整1287项通过；官方collector在无LibYAML时不收集C用例，0skip不表示C通过，不安装发行版PyYAML冒充候选。

| 任务 | 独立业务价值 | 授权与验收 |
| --- | --- | --- |
| YY-U01 理解 | 配置标量和标识类型 | on／012／引号／BaseLoader精确控制；只读 |
| YY-C01 咨询 | 标签选择与业务类型／范围 | 未知tag拒绝和无效业务值接受；不运行unsafe |
| YY-U02 理解 | 别名共享和循环引用 | 有界合成身份检查；不展开循环图 |
| YY-U03 理解 | 值往返不等于注释／顺序保真 | load/dump再解析与原字节对照；无需库修改 |
| YY-C02 咨询 | 重复语义键政策 | composed原始pair、最后值及True／1碰撞；不伪称自动拒绝 |
| YY-P01 方案 | 延迟多文档验收与整体发布 | 第二文档错误、有效多文档与单文档入口对照；不实施事务 |
| YY-D01 诊断 | 完整文档与实际mark | 按请求披露／无材料正常收口；不猜错误 |

五场景七项非修改任务，实际现有API已能支持理解或调用方政策，不为数量制造改库任务或虚假依赖。原生、业务、模拟与交付分别验收；正式状态以后续admission为准。
