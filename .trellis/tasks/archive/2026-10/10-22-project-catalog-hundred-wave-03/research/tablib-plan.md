# tablib实际任务表

固定来源：https://github.com/jazzband/tablib@966876c76a6378557c1951badc1665b4d1375875。

本表由实际逐仓源码核对后的已冻结草稿重算；公开／披露材料、独立私有期望和授权以同名manifest及逐项原件为准，不把测试或分支另计任务。

| 任务 | 类型 | 用户目标 | 验收与授权 |
| --- | --- | --- | --- |
| TB-U01 | understand | 解释CSV表头与文本值 | 只读，不接受代码检查点；verification/TB-U01.native.json |
| TB-U02 | understand | 解释导出格式器与原始单元格 | 只读，不接受代码检查点；verification/TB-U02.native.json |
| TB-C01 | consult | 明确电子表格公式导出策略 | 只读，不接受代码检查点；verification/TB-C01.native.json |
| TB-P01 | plan | 规划批量追加的失败发布边界 | 只读，不接受代码检查点；verification/TB-P01.native.json |
| TB-M01 | modify | 修复商品字典记录的字段错位 | 仅允许library/src/tablib/core.py、app/test_dict_import.py；verification/TB-M01.native.json |
| TB-D01 | diagnose | 诊断首列派生字段的后续错位 | 只读，不接受代码检查点；实际材料消费与语义评审；材料不足合法收口 |

原生完整集合与实际资源见同名准入JSON；产品链／页面／API／数据库／Git／Docker通过后才列为本地正式交付。模型调用0，未推送或部署。
