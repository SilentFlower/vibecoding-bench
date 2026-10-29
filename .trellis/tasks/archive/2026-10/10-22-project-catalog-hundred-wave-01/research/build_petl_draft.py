"""制作已有PETL能力和真实交换边界的独立订单表任务。"""
from draft_content import build_project


def main() -> None:
    """生成四场景八项，只使用本地合成表与临时CSV。@return None。"""
    materials = {
        'materials/lazy-source.py': '''import petl as etl

rows = [("sku", "qty"), ("001", "2"), ("002", "3")]
reads = []
class Source:
    """提供合成可重读订单表。"""
    def __iter__(self):
        """记录读取次数。@return 当前订单表的行迭代器。"""
        reads.append("read")
        return iter(rows)
view = etl.convert(Source(), "qty", int)
one_shot_view = etl.convert(iter(rows), "qty", int)
''',
        'materials/replay-policy.md': 'Inspect reads before consuming the reusable view; use view.list() for each of two controlled traversals, replace rows[1] with ("001","7"), then use view.list() again. Separately compare list(view), which can request a length hint, and one_shot_view.list() across two traversals. Compare also the first list(one_shot_view) attempt on a fresh one-shot source. A preview/report job traverses an ETL view more than once and expects a stable snapshot. Compare the supplied reusable source with a one-shot iterator, and explain which guarantees need explicit application materialization or a replayable source. The complete source/consumption sequence is provided; do not assume a library cache. No files may be changed.\n',
        'materials/conversion.json': '[["sku","qty"],["001","2"],["002","bad"]]\n',
        'materials/conversion-policy.md': 'Convert qty with int under default error behavior, errorvalue="invalid", failonerror=True and failonerror="inline". Compare view construction with actual iteration. For strict mode read the header and first valid row before requesting the invalid row. The application must reject a bad order file rather than publish silent replacement values; plan an explicit consume/validate/publication boundary without code changes.\n',
        'materials/join.json': '{"orders":[["sku","qty"],["A",1],["A",2],["B",3]],"prices":[["sku","price"],["A",10],["A",20]]}\n',
        'materials/join-policy.md': 'Compare join and leftjoin with explicit key="sku" for the supplied complete tables. The business later requires one approved price per SKU; explain why the supplied duplicates do not satisfy it and what uniqueness or deterministic aggregation decision must precede the join. Do not silently select a row, invent a missing cardinality constraint or change the library.\n',
        'materials/orders.csv': 'sku,qty,label\n001,2,"茶,hot"\n002,3,coffee\n',
        'materials/csv-policy.md': 'Read the supplied UTF-8 CSV with fromcsv, explicitly convert qty using int while preserving SKU strings, then write/reread via tocsv/fromcsv in a dedicated temporary directory. Separately export a table with rows ("A",None) and ("B","") under header ("id","value"). The receiving application needs a deliberate missing-versus-empty policy. No real file access or implicit numeric inference is authorized.\n'}
    definitions = [
        ('PE-U01', 'understand', '解释惰性表视图的实际拉取与重读',
            'Trace the supplied reusable-source convert view before consumption, after two traversals, and after changing the underlying row before a third traversal. Is it a frozen snapshot? Do not edit files.',
            ['materials/lazy-source.py', 'materials/replay-policy.md'], 'explained',
            'Constructing convert does not pull this source. Explicit view.list() traverses the reusable source once each time; the first two results match and a third sees qty7 after source mutation. Builtin list(view) can additionally call the inherited enumerating __len__ for a length hint, causing another traversal. The view is neither a cached immutable snapshot nor guaranteed to be read exactly once by every consumer.', ['convert_view_is_lazy_and_reiterates_source', 'builtin_list_length_hint_adds_a_traversal']),
        ('PE-C01', 'consult', '为重复读取明确可重读源或物化边界',
            'Advise how to satisfy the supplied stable repeated-read requirement. Compare the exact one-shot iterator example with the reusable source and identify an appropriate size/replay policy using existing capabilities. Do not modify files.',
            ['materials/lazy-source.py', 'materials/replay-policy.md'], 'advice_with_limits',
            'The explicit one_shot_view.list() first traversal consumes the source and a second cannot recover the header, raising FieldSelectionError. Builtin list(view) can already exhaust a one-shot source via the inherited __len__ before its actual traversal. Existing view.list() or list(iter(view)) avoids that outer length hint, but does not make the source replayable. Use a replayable source or an explicit size/storage-bounded snapshot; do not promise automatic caching or stable data against source changes.', ['one_shot_source_is_not_a_replay_cache', 'builtin_list_length_hint_adds_a_traversal']),
        ('PE-U02', 'understand', '解释数量转换的替代值和异常策略',
            'Trace all supplied qty conversion policies on the complete table. Give the good/invalid row values and distinguish a replacement marker from an exception object or raised error. Do not edit files.',
            ['materials/conversion.json', 'materials/conversion-policy.md'], 'explained',
            'The good qty becomes integer2. Default failure replacement is None; explicit errorvalue supplies invalid; inline mode embeds the actual ValueError object; failonerror=True propagates ValueError during iteration. Do not equate an inline exception or replacement value with a clean converted number.', ['conversion_error_policies_are_explicit']),
        ('PE-C02', 'consult', '在消费时校验完整订单后再发布',
            'Plan the supplied reject-bad-file policy with current conversion options and lazy consumption behavior. Explain what must happen before publication and how partial consumption affects side effects. No implementation is authorized.',
            ['materials/conversion.json', 'materials/conversion-policy.md'], 'advice_with_limits',
            'Use an explicit strict/error-accounting policy and actually consume/validate all relevant rows before an irreversible publication or under a real staged/transaction boundary. The header and valid row can be yielded before the bad row raises; constructing a strict view is not validation success and prior external side effects are not undone by iteration.', ['strict_conversion_fails_during_consumption']),
        ('PE-U03', 'understand', '解释重复键关联的真实输出基数',
            'Trace join and leftjoin for the supplied order/price tables and explicit key. Give matching combinations and treatment of unmatched B. Does either operation choose one A price automatically? Do not edit files.',
            ['materials/join.json', 'materials/join-policy.md'], 'explained',
            'Two A order rows times two A price rows produce four combinations. Inner join has four data rows; leftjoin adds B/3/None for five data rows, in addition to the header. Neither operation chooses or enforces one price per A automatically.', ['duplicate_keys_produce_all_matching_combinations', 'left_join_preserves_unmatched_row']),
        ('PE-C03', 'consult', '在一价一键规则明确后再关联',
            'Advise how to meet the supplied one-approved-price-per-SKU requirement given the actual duplicate table. Identify the needed business decision/validation before using existing joins. Do not modify the library or silently pick an arbitrary price.',
            ['materials/join.json', 'materials/join-policy.md'], 'advice_with_limits',
            'Validate a one-price-per-SKU key constraint or obtain a specified deterministic version/aggregation rule before joining. Explain the current four-combination result as normal duplicate-key behavior, not automatic selection or a missing existing join feature. Do not invent approval order, silently take first/last or call the supplied data already unique.', ['duplicate_keys_produce_all_matching_combinations']),
        ('PE-U04', 'understand', '解释CSV字符串、前导零和显式数量转换',
            'Trace the supplied CSV extraction, qty conversion and temporary roundtrip. Explain actual field types, SKU001, quoted comma and Unicode behavior. Do not access real files or edit project files.',
            ['materials/orders.csv', 'materials/csv-policy.md'], 'explained',
            'fromcsv produces string data, so SKU001 and qty text2 remain strings until qty is explicitly converted. Quoting preserves 茶,hot as one field, and UTF-8 roundtrip preserves the original string rows. Converting qty must leave the SKU string/leading zeros unchanged; no automatic numeric inference is promised.', ['csv_reads_strings_and_preserves_selected_fields']),
        ('PE-P01', 'plan', '规划缺失值与空字符串的交换协议',
            'Plan the supplied CSV exchange so the receiver can distinguish missing None from an empty string where required. Ground the proposal in the actual default roundtrip and existing APIs; identify encoding/schema decisions explicitly without implementing changes.',
            ['materials/orders.csv', 'materials/csv-policy.md'], 'planned_with_explicit_exchange_policy',
            'Ordinary CSV writes both None and empty string as an empty cell, so default rereading cannot restore the distinction. Define an explicit missing-value encoding plus collision/escape and receiver schema policy, or choose a format that represents the types. Preserve string identifiers, UTF-8 and quoting, and do not claim an unprovided reversible sentinel convention is built in.', ['csv_reads_strings_and_preserves_selected_fields', 'plain_csv_collapses_none_and_empty_string'])]
    scenes = [('PE-S01', '惰性订单表视图', '区分重执行、一次源和稳定快照要求', ['PE-U01', 'PE-C01']),
        ('PE-S02', '订单数量转换与拒绝策略', '按真实消费时机选择错误和发布边界', ['PE-U02', 'PE-C02']),
        ('PE-S03', '订单与价格表关联', '解释关联基数并明确一价一键的业务规则', ['PE-U03', 'PE-C03']),
        ('PE-S04', 'CSV交换保真', '保留标识符和文本，并明确缺失值协议', ['PE-U04', 'PE-P01'])]
    build_project('petl', {'title': 'PETL订单表流转工作场景', 'category': '本地ETL与表交换',
        'description': '固定真实源码上的惰性表、转换错误、重复键关联和CSV协议八项独立只读任务。'},
        definitions, scenes, materials)


if __name__ == '__main__':
    main()
