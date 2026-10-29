"""制作不要求改库的配置场景，已有能力必须按已有能力呈现。"""
from draft_content import build_project


def main() -> None:
    """生成四场景九项真实配置任务。@return None。"""
    reload = '''from pathlib import Path
from tempfile import TemporaryDirectory
from decouple import Config, RepositoryEnv

with TemporaryDirectory() as directory:
    path = Path(directory) / ".env"
    path.write_text("VB_CASE_LABEL=first\\n", encoding="utf-8")
    config = Config(RepositoryEnv(str(path)))
    print(config("VB_CASE_LABEL"))
    path.write_text("VB_CASE_LABEL=second\\n", encoding="utf-8")
    print(config("VB_CASE_LABEL"))
    print(Config(RepositoryEnv(str(path)))("VB_CASE_LABEL"))
'''
    materials = {
        'materials/startup.env': 'VB_CASE_PORT=8000\nVB_CASE_EMPTY=file\nVB_CASE_DEBUG=False\nVB_CASE_MODE=prod\n',
        'materials/startup-events.md': 'Use only the supplied synthetic keys. Set process VB_CASE_PORT=9000 and VB_CASE_EMPTY to the empty string. Construct Config(RepositoryEnv(path)). Read PORT with default 7000, EMPTY with fallback, DEBUG with cast=bool, and MODE with Choices(["dev","prod"]). A key absent from all sources is either read with default=42 and cast=int or without a default. Finally set PORT to empty and MODE to invalid, then read them with int and Choices casts plus defaults.\n',
        'materials/startup-plan.md': 'At process startup, load the explicit local file and environment, validate integer port range, boolean debug flag, allowed mode and a list of hosts, collect field errors without exposing sensitive values, and publish one complete immutable application configuration only after validation. Use existing Config/Csv/Choices or explicit callables. Do not claim an existing schema declaration or aggregate-validation API that is absent in the pinned source.\n',
        'materials/reload-symptom.md': 'An application reports that editing its local configuration file does not change a later read. The actual repository construction, reads, file edit sequence and relevant environment override state have not been supplied. Do not assign a cause yet.\n',
        'disclosure/reload.py': reload,
        'disclosure/reload-events.md': 'No VB_CASE_LABEL environment override is present for this synthetic reproduction. Its actual output is first, first, second. The same Config/RepositoryEnv pair is reused for the first two reads.\n',
        'disclosure/unavailable.md': 'The actual repository construction, read/edit sequence and relevant environment override state cannot be provided. No additional incident evidence is available.\n',
        'materials/reload.py': reload,
        'materials/reload-events.md': 'The synthetic key is absent from the environment for the file comparison. Separately, the same Config can be called with process VB_CASE_LABEL=environment-one and again after changing that environment value to environment-two. Do not inspect real application or ancestor configuration.\n',
        'materials/encoding-reproduction.md': 'A temporary .env is written as UTF-8 with an initial U+FEFF before VB_CASE_TITLE=咖啡 and another key VB_CASE_INSIDE=a<U+FEFF>b. Compare RepositoryEnv(path) and RepositoryEnv(path, encoding="utf-8-sig"). Only the first BOM is an encoding marker; the embedded value character must remain. No library modification is requested.\n',
        'materials/simple-dialect.env': 'export VB_CASE_EXPORT=value\nVB_CASE_HASH=a#b\nVB_CASE_EQUALS=a=b\nVB_CASE_QUOTED="coffee beans"\n',
        'materials/list-casts.py': r'''from decouple import Config, Csv

print(Csv()("coffee#roast,tea"))
print(Csv()(r"\d+,tea"))
print(Csv()("coffee,,tea"))
print(Csv()('"coffee, beans",tea'))
print(Csv(cast=int, post_process=tuple)("1, 2"))

config = Config({"VB_CASE_LIST": r"coffee#roast,,\d+"})
''' + '\n',
        'materials/literal-list-requirements.md': 'For the supplied synthetic VB_CASE_LIST value, preserve the literal #, backslash and empty field under standard CSV quoting. Keep existing default Csv behavior for other callers. Assess whether an existing callable cast can meet this need with the Python standard csv module, and explain malformed-quote policy. Do not modify files.\n'}
    definitions = [
        ('DC-U01', 'understand', '解释环境、文件、默认和空值顺序',
            'Trace the supplied synthetic configuration events. Explain which source wins, whether an empty environment value counts as present, and when a missing key uses its default or raises UndefinedValueError. Do not edit files.',
            ['materials/startup.env', 'materials/startup-events.md'], 'explained',
            'Ground precedence in Config.get: environment first, repository second, explicit default last; an empty environment string is present and overrides the file. Distinguish absence from falsy values.', ['environment_file_default_order', 'empty_environment_wins']),
        ('DC-C01', 'consult', '选择已有类型转换并处理失败',
            'Explain bool/int/Choices conversion for the supplied configuration and invalid-value events. Does a conversion error trigger the declared default? Recommend an explicit existing-API validation policy without changing the library.',
            ['materials/startup.env', 'materials/startup-events.md'], 'advice_no_code_change',
            'Use decouple boolean word parsing rather than Python bool(nonempty_text), distinguish defaults on absence from cast failures, and handle ValueError for invalid int/choice explicitly without claiming automatic fallback.', ['existing_casts_observed', 'cast_errors_not_fallback']),
        ('DC-P01', 'plan', '规划启动配置校验和完整发布',
            'Plan the supplied startup validation workflow with current Config, Csv, Choices or explicit callables. Include source precedence, range/choice checks, field-error collection and publication only after complete validation. Do not implement changes or invent a built-in schema API.',
            ['materials/startup.env', 'materials/startup-events.md', 'materials/startup-plan.md'], 'viable_plan_no_library_change',
            'Give a workable application-layer validation and complete-publication plan using real APIs. Treat cast errors explicitly, add port-range checks separately, and do not claim built-in aggregate schema validation or atomic environment snapshots.', ['environment_file_default_order', 'existing_casts_observed', 'cast_errors_not_fallback']),
        ('DC-D01', 'diagnose', '先取读取时序再判断配置不更新',
            'Investigate the supplied stale-file symptom. Request the actual repository construction, file-edit/read sequence and relevant environment override state before assigning a cause. Diagnose actual disclosed evidence only; if unavailable, explain the limit and evidence plan. Do not edit files.',
            ['materials/reload-symptom.md'], 'diagnosed_no_code_change',
            'The initial symptom is insufficient. Request construction and timing plus relevant override state or an equivalent reproduction. Infer a supported explanation only after evidence; insufficient_information is legitimate when material is unavailable. Do not assume automatic reload or a cause before disclosure.', None),
        ('DC-C02', 'consult', '区分文件快照和动态环境读取',
            'Explain the complete supplied file-reload reproduction and the separate environment-change comparison. Recommend an explicit existing-API reload/publication policy, including consistency tradeoffs, without adding a library reload method or changing files.',
            ['materials/reload.py', 'materials/reload-events.md'], 'advice_with_limits',
            'RepositoryEnv reads a file at construction; a new repository sees the new file while the old one retains its data. Config reads environment on each call. Reconstruct and deliberately publish a validated application configuration; do not invent automatic file watching or an atomic multi-key snapshot.', ['file_repository_is_snapshot', 'environment_reads_remain_dynamic']),
        ('DC-U02', 'understand', '用已有编码参数识别文件首BOM',
            'Explain the supplied BOM reproduction under default UTF-8 and explicit utf-8-sig. Show why the first key is affected and whether an existing API solves it, preserving the embedded U+FEFF inside a value. Do not edit files.',
            ['materials/encoding-reproduction.md'], 'explained_with_existing_solution',
            'Default utf-8 retains the leading U+FEFF in the first key. Existing encoding=utf-8-sig handles the initial BOM without deleting embedded value characters. Do not require a library patch or global character stripping.', ['existing_encoding_handles_bom']),
        ('DC-C03', 'consult', '明确ENV简单方言与shell的区别',
            'Explain how the actual RepositoryEnv reads the supplied export, #, equals and quoted lines. Is it a shell or a universal dotenv parser? Recommend a compatible input/application policy without executing shell syntax or modifying the library.',
            ['materials/simple-dialect.env'], 'advice_with_limits',
            'Ground the answer in split-on-first-equals and outer-quote removal: export remains part of the key, while unquoted # and later equals remain value text. Do not claim shell execution, variable interpolation or universal dotenv syntax.', ['simple_env_dialect_observed']),
        ('DC-U03', 'understand', '解释Csv的shlex与后处理语义',
            'Trace the supplied Csv calls, including #, backslashes, consecutive delimiters, a quoted comma and int/tuple postprocessing. Distinguish this existing helper behavior from complete RFC-style CSV field preservation. Do not edit files.',
            ['materials/list-casts.py'], 'explained',
            'Explain shlex comment/escape rules and dropped empty fields, retain the quoted comma as one value, and describe per-item cast then post_process. Do not call the default helper a lossless standard CSV parser.', ['shlex_comment_and_escape_observed', 'csv_helper_drops_empty_fields', 'quoted_comma_and_postprocess']),
        ('DC-C04', 'consult', '用已有callable cast满足字面CSV保真',
            'Meet the supplied literal CSV requirement using existing Config cast support where possible. Preserve #, backslash and the empty field, keep default Csv compatibility, and explain quote/error handling. Decide whether changing the library is necessary; do not edit files.',
            ['materials/list-casts.py', 'materials/literal-list-requirements.md'], 'advice_no_code_change',
            'Provide a valid callable such as a standard csv.reader-based cast for this one-record value, preserving all literal fields with an explicit malformed-quote policy. Keep existing Csv semantics for other callers; a custom cast avoids a required library change.', ['existing_callable_cast_preserves_fields'])]
    scenes = [('DC-S01', '应用启动配置与验证', '理解来源并规划显式启动校验', ['DC-U01', 'DC-C01', 'DC-P01']),
        ('DC-S02', '配置文件变化与最小取证', '区分文件快照、环境变化和重载策略', ['DC-D01', 'DC-C02']),
        ('DC-S03', '文件编码与ENV输入方言', '用实际解析能力解决输入兼容问题', ['DC-U02', 'DC-C03']),
        ('DC-S04', '列表配置与字面字段', '区分shlex助手和标准CSV需求', ['DC-U03', 'DC-C04'])]
    build_project('python-decouple', {'title': 'Python-decouple应用配置工作场景', 'category': '应用配置与输入语义',
        'description': '固定真实源码上的配置优先级、验证、取证、文件快照、编码和列表咨询；四场景九项无需改库任务。'},
        definitions, scenes, materials,
        branches={'DC-D01': [{'id': 'reload-evidence', 'when': 'Actual construction, file-edit/read timing and relevant environment override state have not been disclosed, the conversation does not say they are unavailable, and the answer reasonably requests them or an equivalent sufficient reproduction.',
            'materials': ['disclosure/reload.py', 'disclosure/reload-events.md']}]},
        extra_entries={'DC-S02': [{'id': 'diagnose_only', 'task_ids': ['DC-D01']},
            {'id': 'unavailable', 'task_ids': ['DC-D01'], 'materials': ['disclosure/unavailable.md']}]})


if __name__ == '__main__':
    main()
