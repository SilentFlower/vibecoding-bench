# 业务确认

路线08：parsedate/parsedatetime的OverflowError与既有ParserError同遵IGNORE/SET_NULL/default原错；超大真实年份验收，正常日期与空值/格式选项保留，不捕获所有异常。

请先调查、澄清并确认方案再实施。公开样例不是全部验收边界；独立失败必须返工。
