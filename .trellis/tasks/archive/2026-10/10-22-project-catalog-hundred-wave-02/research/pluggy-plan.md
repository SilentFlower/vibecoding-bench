# Pluggy场景任务表

固定提交0224f79fc75efadaafe24dbab9deee2ff616ecd7、MIT、完整81个Git文件。已读AGENTS转引CLAUDE及全部13个src/pluggy Python文件，实际PluginManager／HookCaller／markers／HookImpl／_multicall／Result／tracing定义与原配置。全部观察只注册内存合成插件，不发现真实分发、不运行宿主插件。

当前目标镜像完整225项通过。Pluggy本身是pytest依赖，环境不安装另一份Pluggy，私有venv绑定真实候选src和从固定提交核出的SCM元数据。初次只缺Repository元数据导致一项原测试失败，已按原pyproject全部project.urls补充私有元数据，失败原件保留；没有改源码、原测试或warning政策。

| 任务 | 独立业务价值 | 授权与验收 |
| --- | --- | --- |
| PG-U01 理解 | 优先级、后注册先调用与None过滤 | 精确结果顺序及Last副作用；只读 |
| PG-C01 咨询 | 首个结果的合法False／0 | None才触发fallback；无需改库 |
| PG-U02 理解 | 协议默认与短签名兼容 | APP／EXPLICIT及短实现控制；只读 |
| PG-C02 咨询 | 初始化pending核验 | 普通未知与明确optional对照；不加载真实插件 |
| PG-U03 理解 | 单报告排除子集 | 子集／完整调用与注册身份保持；无需全局修改 |
| PG-P01 方案 | 历史载荷快照归属 | 可变nested载荷与owned deepcopy重放；不伪称持久化／事务 |
| PG-D01 诊断 | 标记命名空间与注册证据 | 披露完整marker复现或无材料收口；不猜执行失败 |

五场景七项非修改，既有API解释或调用方方案即可满足，不以改库数量充任务。完整原生、业务、产品链与交付分别验收，实际正式状态以后续admission为准。
