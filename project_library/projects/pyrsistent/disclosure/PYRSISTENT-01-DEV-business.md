# 业务确认

路线01：CheckedPMap递归键/值构造及可选pmap_field完整传递ignore_extra；默认拒绝额外字段、已有实例复用，类型和不变量错误不吞。多层map/record/class及None实际验收，普通非checked工厂不强加参数。

请先调查、澄清并确认方案再实施。公开样例不是全部验收边界；独立失败必须返工。
