# webcolors实际任务表

固定来源：https://github.com/ubernostrum/webcolors@6c8da6832eb4ae2591a1883a0d1371263d6cd4db。

本表由实际逐仓源码核对后的已冻结草稿重算；公开／披露材料、独立私有期望和授权以同名manifest及逐项原件为准，不把测试或分支另计任务。

| 任务 | 类型 | 用户目标 | 验收与授权 |
| --- | --- | --- | --- |
| WC-U01 | understand | 解释命名颜色的规范范围 | 只读，不接受代码检查点；verification/WC-U01.native.json |
| WC-U02 | understand | 区分简写归一化与严格颜色格式 | 只读，不接受代码检查点；verification/WC-U02.native.json |
| WC-C01 | consult | 明确通道越界时的拒绝策略 | 只读，不接受代码检查点；verification/WC-C01.native.json |
| WC-C02 | consult | 避免历史兼容算法接受无效颜色 | 只读，不接受代码检查点；verification/WC-C02.native.json |
| WC-P01 | plan | 规划颜色规范化与原始值保存 | 只读，不接受代码检查点；verification/WC-P01.native.json |
| WC-D01 | diagnose | 诊断CSS4颜色往返不一致 | 只读，不接受代码检查点；实际材料消费与语义评审；材料不足合法收口 |

原生完整集合与实际资源见同名准入JSON；产品链／页面／API／数据库／Git／Docker通过后才列为本地正式交付。模型调用0，未推送或部署。
