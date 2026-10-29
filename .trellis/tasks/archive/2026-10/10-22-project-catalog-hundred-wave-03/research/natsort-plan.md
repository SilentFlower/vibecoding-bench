# natsort实际任务表

固定来源：https://github.com/SethMMorton/natsort@e9a3a2a307580a1f2be8c57bba50fba45789ada0。

本表由实际逐仓源码核对后的已冻结草稿重算；公开／披露材料、独立私有期望和授权以同名manifest及逐项原件为准，不把测试或分支另计任务。

| 任务 | 类型 | 用户目标 | 验收与授权 |
| --- | --- | --- | --- |
| NS-U01 | understand | 解释标识中的负号策略 | 只读，不接受代码检查点；verification/NS-U01.native.json |
| NS-U02 | understand | 区分数值和版本号排序 | 只读，不接受代码检查点；verification/NS-U02.native.json |
| NS-C01 | consult | 选择文件清单的路径排序策略 | 只读，不接受代码检查点；verification/NS-C01.native.json |
| NS-C02 | consult | 明确字节文件名的解码边界 | 只读，不接受代码检查点；verification/NS-C02.native.json |
| NS-P01 | plan | 规划并列字段的一致重排 | 只读，不接受代码检查点；verification/NS-P01.native.json |
| NS-D01 | diagnose | 诊断前导零平局的顺序变化 | 只读，不接受代码检查点；实际材料消费与语义评审；材料不足合法收口 |

原生完整集合与实际资源见同名准入JSON；产品链／页面／API／数据库／Git／Docker通过后才列为本地正式交付。模型调用0，未推送或部署。
