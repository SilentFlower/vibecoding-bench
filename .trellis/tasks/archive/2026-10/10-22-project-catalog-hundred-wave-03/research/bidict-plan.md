# bidict实际任务表

固定来源：https://github.com/jab/bidict@299fedc89f1d70d5d41cf7922564b376d3e2d435。

本表由实际逐仓源码核对后的已冻结草稿重算；公开／披露材料、独立私有期望和授权以同名manifest及逐项原件为准，不把测试或分支另计任务。

| 任务 | 类型 | 用户目标 | 验收与授权 |
| --- | --- | --- | --- |
| BI-U01 | understand | 区分赋值与严格插入 | 只读，不接受代码检查点；verification/BI-U01.native.json |
| BI-U02 | understand | 理解反向标识视图的实时性 | 只读，不接受代码检查点；verification/BI-U02.native.json |
| BI-C01 | consult | 选择有损冲突处理策略 | 只读，不接受代码检查点；verification/BI-C01.native.json |
| BI-C02 | consult | 选择稳定导出快照 | 只读，不接受代码检查点；verification/BI-C02.native.json |
| BI-P01 | plan | 规划双射批量导入的事务边界 | 只读，不接受代码检查点；verification/BI-P01.native.json |
| BI-D01 | diagnose | 诊断有序映射比较未发现顺序变化 | 只读，不接受代码检查点；实际材料消费与语义评审；材料不足合法收口 |

原生完整集合与实际资源见同名准入JSON；产品链／页面／API／数据库／Git／Docker通过后才列为本地正式交付。模型调用0，未推送或部署。
