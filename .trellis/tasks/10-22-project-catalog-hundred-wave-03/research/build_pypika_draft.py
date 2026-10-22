"""制作基于真实商品查询、数据库绑定和构造器归属的独立任务。"""
from draft_content import build_project


def main() -> None:
    """冻结四场景六任务，保留真实SQLite结果与只读授权。@return None。"""
    materials = {
        'materials/items.md': 'Use a synthetic in-memory SQLite table items(id INTEGER,name TEXT,active INTEGER,price INTEGER,deleted_at TEXT). Rows in insertion order are (1,Tea,0,20,NULL),(2,Book,1,20,2026-10-20),(3,Pen,1,5,NULL),(4,O\'Reilly,1,30,NULL). The Python string for the fourth name is "O\'Reilly". Use the supplied PyPika source; no external database or file edits.\n',
        'materials/predicates.md': 'Compare Query.from_(t).select(t.id).where((t.active == 1) and (t.price > 10)) with the same expression using parenthesized &. For a separate not-deleted view compare where(t.deleted_at == None) with where(t.deleted_at.isnull()). Explain the actual generated predicates and selected item IDs for each complete control. Do not silently correct the original expressions or claim a database query builder validates application intent.\n',
        'materials/binding.md': 'A product lookup must use the actual name "O\'Reilly". Serialize Query.from_(t).select(t.id).where(t.name == supplied_name) with a fresh NamedParameter,then pass its get_parameters() separately to SQLite.execute. Include the synthetic supplied_name "x\' OR 1=1 --" as a counterexample that must remain a value. Explain SQL and parameters separately,driver paramstyle and the limits of value binding; no library changes or real database.\n',
        'materials/identifiers.md': 'A configurable report has table name order and column name select. Compare reserved.select,reserved.field("select") and reserved["select"]. Generate the projection with actual MySQLQuery and PostgreSQLQuery. Advise an application-owned allowed-column map and actual dialect selection. Identifiers are not value parameters,and quoting does not authorize arbitrary report fields. Only generated SQL is observed for these dialects; no MySQL/PostgreSQL execution or connection is available. No edits.\n',
        'materials/export-plan.md': 'Serialize two item-name lookups,first O\'Reilly and then Tea,with the same NamedParameter instance. Retain both a direct reference from get_parameters() and dict(get_parameters()) after the first serialization. Explain what the second serialization changes and plan independent reproducible query exports. Specify collector lifetime,SQL/parameter pairing,snapshot ownership and roundtrip controls. Do not implement a new exporter or claim the collector automatically resets.\n',
        'disclosure/discarded-return.md': 'The complete synthetic code is t=Table("items"); q=Query.from_(t).select(t.id); q.where(t.active == 1); original_sql=q.get_sql(). The original SQL is SELECT "id" FROM "items" and the selected IDs are [1,2,3,4]. In a separate control,captured=q.where(t.active == 1) emits SELECT "id" FROM "items" WHERE "active"=1 and returns [2,3,4]. q is captured is False. The pinned source and complete items table are available. No exception occurs. Diagnose the cause and show an application-level correction without editing files or changing the library.\n',
        'disclosure/unavailable.md': 'The calling code,query construction order,returned object usage,generated SQL and complete synthetic table/results cannot be supplied. There is no complete reproduction to distinguish a discarded return,changed predicate or database/data difference.\n'}
    materials['disclosure/items.md'] = materials['materials/items.md']
    definitions = [
        ('PQ-U01', 'understand', '解释商品筛选条件为何丢失',
            'Explain the complete Python and versus parenthesized & controls and actual selected IDs. No edits.',
            ['materials/items.md', 'materials/predicates.md'], 'explained',
            'Python and evaluates the truth of the first criterion and returns the second here: IDs1,2,4. Parenthesized & builds both SQL predicates and returns2,4. Distinguish Python evaluation from SQL Boolean composition and preserve the supplied counterexample rows; equivalent correct explanations are valid.',
            ['python_boolean_and_drops_a_sql_predicate']),
        ('PQ-U02', 'understand', '追踪空值条件与未删除商品结果',
            'Explain the complete None equality versus isnull controls with actual SQL/SQLite results. No edits.',
            ['materials/items.md', 'materials/predicates.md'], 'explained',
            'The pinned equality emits =null,which selects no rows under SQL NULL semantics. isnull emits IS NULL and returns1,3,4. Do not say Python None comparison is automatically rewritten or call this empty result proof of missing rows. Use the actual table and native API.',
            ['sql_null_requires_null_predicate_instead_of_equality']),
        ('PQ-C01', 'consult', '为含引号的商品名选择参数绑定',
            'Advise and explain the existing NamedParameter/SQLite controls,including the supplied counterexample value. Do not edit files.',
            ['materials/items.md', 'materials/binding.md'], 'advice_no_code_change',
            'Use a fresh NamedParameter and separate its actual dictionary from SQL when calling the matching driver. O\'Reilly stays an unquoted raw parameter value and returns4;the supplied SQL-like value returns no rows and never becomes query structure. Match paramstyle to the driver,do not interpolate formatted values or claim parameters bind identifiers. No library patch is required.',
            ['named_values_are_bound_separately_from_query_text']),
        ('PQ-C02', 'consult', '处理方法重名列与数据库方言引用',
            'Advise identifier lookup,allowed-column ownership and actual dialect quoting from the complete controls. No edits or database connection.',
            ['materials/identifiers.md'], 'advice_no_code_change',
            'Table.select is an existing method;field("select") or ["select"] obtains the field explicitly. Actual MySQLQuery emits backticks while PostgreSQLQuery emits double quotes for order/select. Choose real dialect and an explicit allowed-column map;neither arbitrary attribute existence nor value placeholders validate report-column authorization. These are serialized controls,not proven backend executions.',
            ['identifier_lookup_and_dialect_quoting_are_explicit_controls']),
        ('PQ-P01', 'plan', '规划独立查询导出的参数快照',
            'Plan reproducible independent SQL/parameter exports from the shared-collector controls. No implementation.',
            ['materials/items.md', 'materials/export-plan.md'], 'planned_without_library_change',
            'NamedParameter accumulates values and increments placeholders across serializations;get_parameters returns its live dictionary. The retained reference grows from param1 to param1/param2 while a copied first snapshot remains unchanged. Prefer a fresh collector per independent export and freeze SQL with a copied/serialized matching parameter map;test two exports and subsequent mutation. Do not invent reset,deep immutability or driver-independent execution guarantees.',
            ['parameter_collectors_accumulate_and_require_snapshot_ownership']),
        ('PQ-D01', 'diagnose', '先核完整构造过程再解释过滤未生效',
            'A product query still returns inactive items after a where call. Request the complete construction/calling code,returned-object usage,generated SQL and synthetic rows/results before diagnosing. No edits.',
            [], 'diagnosed_or_information_requested',
            'Use only actually consumed evidence. Request missing complete reproduction before selecting a cause. If complete evidence is delivered,trace builder/QueryBuilder copy behavior and the original versus captured-return SQL/IDs;advise retaining the returned query without a library patch. If evidence is unavailable,insufficient_information is a legitimate result;do not assert the observed cause from an unconsumed private reproduction.', None)]
    scenes = [
        ('PQ-S01', '商品筛选语义', '核真实条件与空值结果', ['PQ-U01', 'PQ-U02']),
        ('PQ-S02', '查询参数与标识', '分清值绑定、字段与方言', ['PQ-C01', 'PQ-C02']),
        ('PQ-S03', '查询导出归属', '保存相互独立的SQL和参数', ['PQ-P01']),
        ('PQ-S04', '过滤调用诊断', '先核完整调用与返回值', ['PQ-D01'])]
    build_project('pypika', {'title': 'PyPika商品查询工作场景', 'category': 'SQL条件、参数与构造归属',
        'description': '商品条件、空值、参数绑定、标识方言、导出快照和过滤诊断六项独立任务。'},
        definitions, scenes, materials,
        branches={'PQ-D01': [{'id': 'complete-query-reproduction',
            'when': 'The complete construction code,returned-object usage,SQL and synthetic rows/results have not been delivered or declared unavailable,and sufficient evidence is reasonably requested.',
            'materials': ['disclosure/discarded-return.md', 'disclosure/items.md']}]},
        extra_entries={'PQ-S04': [{'id': 'unavailable', 'task_ids': ['PQ-D01'],
            'materials': ['disclosure/unavailable.md']}]})


if __name__ == '__main__':
    main()
