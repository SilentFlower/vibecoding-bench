# python-liquid实际场景任务表

固定来源：https://github.com/jg-rp/liquid@878f589adff6cb6bf08ccea7895570f96980248e。

先冻结逐仓已核事实、用户目标和独立验收，再制作内容。各任务不消费未声明的前序答案或代码；披露和材料不足路径不重复计数。

## LQ-U01：解释Liquid条件真值

类型：understand；合法结果：explained。

用户问题与当前控制：Render {% if x %}yes{% else %}no{% endif %} for x=0,"",[],False,None with the supplied Environment defaults. Compare the intended business meaning with Python truthiness. No edits.

独立验收：Liquid treats0,empty string and empty list as truthy;False and None are falsey. Results are yes,yes,yes,no,no. Write an explicit emptiness/value predicate when business logic needs one;do not translate Python if behavior mechanically or treat zero inventory as missing.

公开材料：materials/lq-u01.md

授权：只读，不产生接受代码检查点。

实际业务控制：liquid_truthiness_differs_from_python_for_zero_and_empty_containers。

## LQ-U02：解释默认值过滤器的空值策略

类型：understand；合法结果：explained。

用户问题与当前控制：Render {{ x | default: "fallback" }}|{{ x | default: "fallback", allow_false: true }} for x=0,False,"",None. Explain why this filter differs from a plain if. No edits.

独立验收：Outputs are0|0,fallback|false,fallback|fallback,fallback|fallback. Numeric zero is retained;allow_false preserves explicit False,but empty strings and nil still use the fallback. Define per-field nil/false/empty policy instead of treating default as a generic Python-or or validation function.

公开材料：materials/lq-u02.md

授权：只读，不产生接受代码检查点。

实际业务控制：default_filter_distinguishes_numeric_zero_false_and_empty。

## LQ-U03：解释模板片段的变量作用域

类型：understand；合法结果：explained。

用户问题与当前控制：DictLoader provides p="{{ x }}{% assign x = 'inner' %}". Compare templates that assign x="outer",then include "p" or render "p",then output |{{ x }}. No other globals or named arguments are supplied. No edits.

独立验收：include renders outer and changes the caller local x to inner,so outer|inner. render uses an isolated partial scope with no caller local x and does not change caller x,so |outer. Pass named data explicitly for reusable render snippets;do not call include/render equivalent or infer all globals are inaccessible.

公开材料：materials/lq-u03.md

授权：只读，不产生接受代码检查点。

实际业务控制：include_shares_local_assignments_while_render_has_an_isolated_partial_scope。

## LQ-C01：选择HTML输出的转义策略

类型：consult；合法结果：advice_no_code_change。

用户问题与当前控制：Compare Environment() with Environment(autoescape=True) when rendering {{ x }} and plain context x="<b>A&B</b>". Advise a browser-output policy without displaying or executing the value. No implementation.

独立验收：Default autoescape=False emits the raw string;explicit True emits &lt;b&gt;A&amp;B&lt;/b&gt;. Choose escaping for the actual output context,keep untrusted values plain,and separately review safe/Markup values,custom filters and URL/attribute consumers. This fixed output probe is not a complete sandbox or a promise that every browser context is safe.

公开材料：materials/lq-c01.md

授权：只读，不产生接受代码检查点。

实际业务控制：html_autoescaping_must_be_explicitly_selected_for_plain_context_values。

## LQ-C02：选择模板缺失数据处理方式

类型：consult；合法结果：advice_no_code_change。

用户问题与当前控制：Render A{{ user.name }}B with no user data using default undefined and StrictUndefined. Advise report validation/error handling and optional-field policy. No edits.

独立验收：Default Undefined silently yields AB;StrictUndefined raises UndefinedError when the missing value is consumed. Validate required report data and choose explicit optional fallbacks/error reporting before publication. Distinguish strict variable handling from tag/filter tolerance and do not claim defaults validate completeness.

公开材料：materials/lq-c02.md

授权：只读，不产生接受代码检查点。

实际业务控制：missing_context_is_silent_by_default_and_rejected_by_strict_undefined。

## LQ-P01：规划有资源边界的模板渲染

类型：plan；合法结果：planned_without_library_change。

用户问题与当前控制：Set env.loop_iteration_limit=2 and render {% for x in xs %}{{ x }}{% endfor %} for xs=[1,2] and [1,2,3]. Inspect the default limit and other defined Environment limits. Plan finite rendering budgets,loader isolation and error publication;no implementation or real-service access.

独立验收：The two-item control yields12;the three-item control raises LoopIterationLimitError;the default loop limit is None. Plan explicit loop/output/namespace/context and external process time/memory budgets,restricted template loaders and reviewed filters,plus failure handling without publishing partial reports. Test nested/recursive/oversized cases against actual configured limits. A loop limit alone is not a complete sandbox or application authorization boundary.

公开材料：materials/lq-p01.md

授权：只读，不产生接受代码检查点。

实际业务控制：finite_loop_limit_is_enforced_but_is_not_a_complete_sandbox。

## LQ-D01：诊断复合条件与预期不一致

类型：diagnose；合法结果：diagnosed_or_information_requested。

用户问题与当前控制：A compound Liquid condition differs from a Python-style expectation. Request the complete expression,actual inputs,parser flags and branch output before diagnosing. No edits.

独立验收：Use consumed logical-parser evidence to explain the actual association and propose a separately tested template decomposition. Missing evidence supports insufficient_information;do not assume Python precedence or promise unsupported parentheses.

公开材料：取得合理追问后才披露；材料不足允许合法收口

授权：只读，不产生接受代码检查点。

实际业务控制：核材料消费与语义结论。

完整原生、工程正反例、mock、页面／API／数据库及Git／Docker分别核验；未准入前不正式注册。模型调用0，不push或部署。
