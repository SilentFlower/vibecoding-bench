# Dpath场景任务表

> 状态说明：本文保留设计阶段记录，实际验证与准入以[本项目准入记录](dpath-admission.json)为准。

固定提交15759d96a006fef5278de731cd263b4d839094c3，MIT。已读dpath/__init__.py的_split_path/new/set/get/search/delete/merge、segments.set/_default_creator及MergeType；原生真实nose2入口79项通过，未改用pytest替代。

| 任务 | 真实业务问题 | 材料、授权和验收 |
| --- | --- | --- |
| DP-U01 理解 | 单结果查询默认值是否能吞掉多命中 | 只读，缺失sentinel、多命中ValueError和根对象身份 |
| DP-C01 咨询 | 含/的外部字段怎样保留路径边界 | 只读，序列分段保留字面分隔符，仍说明glob政策 |
| DP-U02 理解 | 更新已有匹配与新建路径的返回和结构 | 只读，set的2／0匹配、新建字面*与数字列表 |
| DP-U03 理解 | 删掉中间项后为何保留None | 只读，列表中间留空、尾删缩短与无匹配异常 |
| DP-C02 咨询 | 字段导出应返回嵌套投影还是路径记录 | 只读，真实list结构与yielded路径值，源保留 |
| DP-U04 理解 | 默认列表合并是否复制输入 | 只读，真实源列表别名及REPLACE对照 |
| DP-P01 方案 | TYPESAFE失败是否等同事务回滚 | 只读，先写added再失败的真实部分更新；隔离副本和发布政策 |
| DP-M01 修改 | 有过滤器时删除不能越过glob范围 | 仅library/dpath/__init__.py和新增app/test_delete_filter.py，实际复现原版误删outside.same；路径与谓词交集、无过滤及分隔符回归 |

四场景八任务，其中七项非修改。工程目标直接给出完整合成复现和授权，不另拆追问凑数；默认和modify_direct入口的工程目标独立可执行，inspect_only只读入口保留列表解释。不声明不真实的答案／代码依赖。

独立参考只修复delete中的条件，并交付4个公开unittest；错误候选将条件误写为匹配或谓词。原版业务／公开测试须失败，参考须通过业务、公开测试和完整79项nose2，错误候选须拒绝；具体实际结果以business/dpath下原件和准入JSON为准，尚未结束的回归不能提前标通过。
