# IceCream场景任务表

> 状态说明：本文保留设计阶段记录，实际验证与准入以[本项目准入记录](icecream-admission.json)为准。

固定提交05af3e95b0080162813bb017de90966bc75f3b91，MIT，完整65项原生unittest通过。已读`IceCreamDebugger.__init__/__call__/format/_format/_formatArgs/_constructArgumentOutput/enable/disable/configureOutput`及包导出；包导出把版本模块字典写入globals，故用类定义文件核候选，不误把`icecream.__file__`的版本文件显示当成源码替换。

| 任务 | 用户业务问题和真实边界 | 授权与正反观察 |
| --- | --- | --- |
| IC-U01 理解 | 调试包装是否复制了数据 | 只读，单参数同一对象、多参数元组、无参None |
| IC-C01 咨询 | 关闭调试后怎样避免昂贵参数表达式执行 | 只读，实际关闭后仍有一次Python先行求值，输出为空 |
| IC-U02 理解 | 已关闭debugger的显式format会不会计算／打印 | 只读，仍返回真实格式文本，collector为空 |
| IC-C02 咨询 | 值格式器遮住值后，源码表达式是否仍可能包含字面 | 只读，在真实文件比较变量与含合成token的表达式；不发布原始trace |
| IC-P01 方案 | 输出配置归哪个组件，前缀何时求值 | 只读，两个独立实例和动态前缀真实顺序；不宣称并发已验 |

三个场景五任务，全部原生观察，无材料不足诊断场景和工程目标；不强造类型覆盖。只用合成数据、可读源码文件和私有collector，不读取真实日志／凭据。正式计数仍等待产品链与页面／API／SQLite及交付校验。
