# 业务确认

required_if在归一化后的真实required阶段检查，即使目标字段缺失也生效。支持兄弟和根条件、False/None与默认判别字段；存在性复用required、nullable和ignore_none_values政策，update及排除规则保持。

方案确认后实施真实源码改动，公开样例不是全部验收边界。禁止修改原始测试、环境或独立验收器。
