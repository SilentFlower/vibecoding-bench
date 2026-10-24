# 业务确认

路线01：独立不可变DisplayVersion保留精确原文，display展示原文、str与比较/hash继续标准规范化；已有Version派生时原文明确None，pickle和只读边界完整验证。

请先调查、澄清并确认方案再实施。公开样例不是全部验收边界；独立失败必须返工。
