# funcy实际场景任务表

固定来源：https://github.com/Suor/funcy@e8febffd57f80db8ca3a55fb1edd0feee2290d61。

先冻结逐仓已核事实、用户目标和独立验收，再制作内容。各任务不消费未声明的前序答案或代码；披露和材料不足路径不重复计数。

## FU-U01：解释惰性管道的执行时点

类型：understand；合法结果：explained。

用户问题与当前控制：A convert callback records its argument and doubles it. Create funcy.map(convert,[1,2,3]),inspect calls,consume one item,then the rest and repeat consumption. Compare funcy.lmap(convert,[4,5]). Explain evaluation and one-shot behavior. No edits.

独立验收：map initially calls nothing;next yields2 and records1;remaining consumption gives4,6 and records2,3. The exhausted iterator yields nothing on a second pass. lmap immediately records4,5 and returns[8,10]. Choose an explicit materialization boundary when later steps need replay or failure detection;do not infer work completed when the iterator was constructed.

公开材料：materials/fu-u01.md

授权：只读，不产生接受代码检查点。

实际业务控制：map_defers_work_and_is_consumed_while_lmap_eagerly_materializes。

## FU-U02：避免空值清理删除有效零值

类型：understand；合法结果：explained。

用户问题与当前控制：Compare list(funcy.keep([None,0,False,"",2,"ok"])) with funcy.filter(lambda value:value is not None,[None,0,False,""]). Explain a quantity/flag cleanup contract. No edits.

独立验收：keep retains only[2,"ok"],discarding all falsey values including0,False and empty text. An explicit non-None predicate retains[0,False,""];choose it if only None means missing. Do not silently remove valid zero quantities or explicit negative flags under a generic cleanup label.

公开材料：materials/fu-u02.md

授权：只读，不产生接受代码检查点。

实际业务控制：keep_discards_all_falsey_values_including_valid_zero_and_false。

## FU-C01：选择记录去重的保留策略

类型：consult；合法结果：advice_no_code_change。

用户问题与当前控制：For rows [{"id":2,"value":"first"},{"id":1,"value":"x"},{"id":2,"value":"last"}],use distinct(rows,key=operator.itemgetter("id")). Advise first/last/conflict semantics and output order. No implementation.

独立验收：The explicit key retains the first id2 record and then id1 in input order;it does not sort,merge or keep the latest duplicate. Choose a business-approved conflict policy and explicit hashable identity key,retain conflict evidence if payload differences matter,and bound seen-set memory for large streams. Do not replace itemgetter with a string shorthand without checking its actual interpretation.

公开材料：materials/fu-c01.md

授权：只读，不产生接受代码检查点。

实际业务控制：distinct_retains_the_first_record_per_explicit_hashable_key。

## FU-C02：评估惰性分流的缓存边界

类型：consult；合法结果：advice_no_code_change。

用户问题与当前控制：A generator logs and yields0,1,2,3. Split with funcy.split(lambda value:value%2==0,source). Exhaust the passed iterator first,inspect the source log,then consume the failed iterator. Advise a long-stream consumption strategy. No edits.

独立验收：The first branch yields0,2 but advances the shared source through all four inputs,buffering1,3 for the second branch. Lazy split therefore does not guarantee bounded memory when branches progress unevenly. Consume with a coordinated bounded policy or explicitly spool bounded inputs;do not claim independent source scans or constant memory.

公开材料：materials/fu-c02.md

授权：只读，不产生接受代码检查点。

实际业务控制：lazy_split_shares_input_and_buffers_the_unconsumed_branch。

## FU-P01：规划重试的业务副作用边界

类型：plan；合法结果：planned_without_library_change。

用户问题与当前控制：A local @retry(3,errors=ValueError,timeout=0) callback appends an effect marker before raising ValueError on its first two calls and succeeding on its third. Inspect markers and plan an idempotent request/retry contract. Do not call services or implement anything.

独立验收：tries3 is three total attempts;the control succeeds on the third with three effect markers. A retry does not roll back prior effects. Plan stable operation identity,deduplication or transactional publication at the actual effect owner,explicit retryable error classification,finite budgets and retained attempts. Do not equate a response failure with an unapplied operation or claim this decorator itself provides exactly-once effects.

公开材料：materials/fu-p01.md

授权：只读，不产生接受代码检查点。

实际业务控制：retry_repeats_prior_side_effects_and_counts_total_attempts。

## FU-D01：诊断缓存列表被下游修改

类型：diagnose；合法结果：diagnosed_or_information_requested。

用户问题与当前控制：A memoized report function seems to return contaminated data. Request the decorator,complete calls,returned object identity and any mutation before diagnosing. No edits.

独立验收：Use consumed cache/reference evidence to distinguish reused mutable return objects from recomputation or key collisions. Missing controls support insufficient_information. Propose a separately tested ownership/copy policy without clearing private cache state or altering package semantics.

公开材料：取得合理追问后才披露；材料不足允许合法收口

授权：只读，不产生接受代码检查点。

实际业务控制：核材料消费与语义结论。

完整原生、工程正反例、mock、页面／API／数据库及Git／Docker分别核验；未准入前不正式注册。模型调用0，不push或部署。
