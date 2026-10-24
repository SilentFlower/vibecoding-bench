# 流程规则诊断报告真实短路条件并保留未执行项

路线04：explain_event明确执行prepare与规则并报告真实pass/fail/skipped/error，遵循短路且不额外评估；不执行迁移回调/改态，与只读结构预览分开。
