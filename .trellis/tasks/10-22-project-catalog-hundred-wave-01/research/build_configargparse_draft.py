"""制作ConfigArgParse来源、列表、布尔取证、格式和重载任务。"""
from draft_content import build_project


def main() -> None:
    """保存五场景八项只读任务，全部来源均为合成显式输入。@return None。"""
    materials = {
        'materials/precedence.md': 'For each comparison construct a fresh ArgumentParser(add_help=False), add --workers with type=int,default=1,env_var=APP_WORKERS. Compare CLI4/env3/config workers=2; then noCLI/env3/config2; then noCLI/noenv/config2; then noCLI/noenv/emptyconfig. Pass explicit args,env_vars and config_file_contents instead of reading real process inputs.\n',
        'materials/source-report.md': 'A separate synthetic parser has --password with env_var=APP_PASSWORD. Parse only explicit {APP_PASSWORD:synthetic-password}. Inspect get_source_to_settings_dict and format_values. A user-facing support summary may show source labels but must not echo secret values. No real account, credential or environment is supplied; do not publish a raw report or modify files.\n',
        'materials/lists.md': 'Fresh parser each time: --tag action=append,default=[base],env_var=APP_TAGS. Compare CLI --tag cli plus env APP_TAGS=["env1","env2"] plus config tag=[cfg]; then env+config withoutCLI; then config only. All values are synthetic. Determine source precedence versus the separate argparse default-list append behavior; do not assume list sources all concatenate.\n',
        'materials/boolean-symptom.md': 'The operator supplied a value intended to disable a switch, yet the parsed switch was enabled. The argument definition, exact CLI/environment/config values and parser call have not been supplied. Investigate before assigning a cause.\n',
        'disclosure/boolean.md': 'Complete synthetic call: parser=ArgumentParser(add_help=False); parser.add_argument("--enabled",type=bool,env_var="APP_ENABLED"); result=parser.parse_args([],env_vars={"APP_ENABLED":"false"}).enabled. No config values or CLI options are supplied. The result is True.\n',
        'disclosure/unavailable.md': 'The argument definition and actual CLI/environment/config values cannot be supplied. There is no further reproduction.\n',
        'materials/boolean-policy.md': 'An opt-in --enabled flag must interpret explicit environment strings true and false, reject unknown maybe, and let an explicit CLI --enabled override a false environment value. Compare current action=store_true with type=bool using separate synthetic parsers and explicit env_vars; no project changes are authorized.\n',
        'materials/sections.ini': '[dev]\nhost=A\n[prod]\nhost=B\n',
        'materials/formats.md': 'Compare DefaultConfigFileParser and existing IniConfigParser bound only to dev with split_ml_text_to_list=False on sections.ini. Separately serialize {message:"line1\\nline2"} with a real embedded newline: compare the default parser with YAMLConfigFileParser round-trip, and retain a simple workers="2" default-format control. The application must retain newline content, not inject additional config keys. No file writes are requested.\n',
        'materials/provider.md': 'A synthetic callable in default_config_files returns a newly created StringIO containing workers=2 on its first invocation and workers=3 on its second. Parse twice with explicit empty args/env_vars and type=int. Plan a reloadable provider contract: invocation count, fresh open streams, parser closure, validation and application publication boundary. No remote secrets service, real config file or implementation is supplied.\n'}
    definitions = [
        ('CA-U01', 'understand', '追踪命令行、环境、配置和默认值优先级',
            'Trace all four complete scalar-source controls and give final typed workers values. Explain which source wins without assuming any real process state or changing files.',
            ['materials/precedence.md'], 'explained',
            'Results are4,3,2,1 with CLI overriding environment, then config, then declared default. Use fresh parsers and explicit inputs. Source precedence is not evidence that an unrelated process environment, config search path or application validation was tested.', ['scalar_precedence_is_cli_environment_config_default']),
        ('CA-C01', 'consult', '展示配置来源而不回显受限字段值',
            'Meet the complete support-summary requirement using current source-reporting APIs. Explain what the supplied report actually contains and define application-owned display filtering. Do not expose a raw report, access real credentials or implement changes.',
            ['materials/source-report.md'], 'advice_with_limits',
            'get_source_to_settings_dict includes the synthetic APP_PASSWORD action/value and format_values prints that value. These APIs provide provenance, not automatic redaction. Build an explicit allowed-field/source summary or redact declared sensitive fields before display, preserving useful source identity without dumping the raw formatted string. No real secret or sanitizer execution is claimed.', ['source_reporting_keeps_values_and_requires_application_policy']),
        ('CA-U02', 'understand', '区分列表来源覆盖和append默认项',
            'Trace all complete append controls and list exact outputs. Explain source selection separately from the nonempty default list behavior of argparse. Do not change files or claim all lower-priority lists merge.',
            ['materials/lists.md'], 'explained',
            'CLI case gives[base,cli], env case[base,env1,env2], config-only[base,cfg]. Lower-priority supplied sources are suppressed, while the declared nonempty default participates in append. List ordering/source precedence and default-list accumulation are distinct policies.', ['append_keeps_declared_defaults_but_selects_one_supplied_source']),
        ('CA-D01', 'diagnose', '先取开关定义和输入再定位意外启用',
            'Investigate the supplied enabled-switch symptom. Request the exact argument/action/type definition, parser call and CLI/env/config inputs before deciding the cause. Diagnose only disclosed evidence or close with an evidence plan if unavailable. Do not change files.',
            ['materials/boolean-symptom.md'], 'diagnosed_no_code_change',
            'Initially request sufficient real definition and source inputs; the symptom cannot establish bool conversion or precedence. Relate only disclosed evidence to current behavior and a compatible remedy, or use insufficient_information when missing. Do not assume type=bool or an overriding CLI before disclosure.', None),
        ('CA-C02', 'consult', '用已有布尔action满足明确开关词汇',
            'Meet the complete opt-in switch requirement with current APIs. Compare actual type=bool and flag controls including true,false,unknown and CLI precedence. No implementation is authorized.',
            ['materials/boolean-policy.md'], 'advice_no_code_change',
            'type=bool calls Python truthiness on a nonempty false string and yieldsTrue. Existing store_true action with environment support recognizes false asFalse and true asTrue, rejects maybe, and explicit CLI --enabled overrides false env. Select the real action or an explicitly strict application parser according to the required CLI shape, not a library repair or bool-string assumption.', ['existing_boolean_action_parses_false_and_rejects_unknown_tokens']),
        ('CA-U03', 'understand', '区分默认节注释和按INI节选配置',
            'Trace the supplied complete INI controls under both current parsers. Give exact selected host values and explain whether default section headings provide namespacing. Do not edit files.',
            ['materials/sections.ini', 'materials/formats.md'], 'explained',
            'DefaultConfigFileParser treats section-heading lines as comments, so the later repeated host wins asB. IniConfigParser explicitly bound todev returnsA. Do not assume the default simplified INI/YAML-like syntax selects a section or prevents cross-section repeated-key replacement.', ['default_section_comments_are_not_selected_ini_sections']),
        ('CA-C03', 'consult', '选择能保留多行值的已有配置格式',
            'Meet the complete newline round-trip requirement with existing serializers. Explain default rejection, the simple valid control and YAML result without replacing newlines or inventing multiline support.',
            ['materials/formats.md'], 'advice_no_code_change',
            'Default serialization rejects embedded newline/CR with ValueError to avoid changing the parsed key structure; the simple workers2 control round-trips. Existing YAMLConfigFileParser can serialize and parse the supplied actual multiline string with content intact. Choose the supported format/dependency deliberately; do not strip newlines silently or claim the simplified format already quotes arbitrary multiline values.', ['multiline_serialization_needs_a_supporting_format']),
        ('CA-P01', 'plan', '规划可重载配置流的创建和关闭责任',
            'Plan the complete synthetic reload-provider requirement using current callable default_config_files support. Give observed invocation/closure/value controls and distinguish parsed validation from application publication. Do not access remote configuration or implement a service.',
            ['materials/provider.md'], 'planned_without_library_change',
            'The provider is invoked for each parse and must return a fresh open readable stream. Two supplied parses yield2 then3 and the parser closes both streams; reusing a closed stream is not valid. Validate the full new configuration before an explicit application-owned publication/recovery boundary and define provider errors/reload serialization. The parser does not itself atomically publish live application state or fetch an unspecified secret service.', ['callable_provider_reopens_and_parser_closes_each_stream'])]
    scenes = [('CA-S01', '来源优先级与展示政策', '解释获胜来源并限定对外可展示字段', ['CA-U01', 'CA-C01']),
        ('CA-S02', '重复选项与默认列表', '区分来源覆盖和原生append默认项', ['CA-U02']),
        ('CA-S03', '布尔开关取证与选择', '先取实际定义再选择已有布尔语义', ['CA-D01', 'CA-C02']),
        ('CA-S04', '配置格式和内容保真', '明确节边界及多行值支持', ['CA-U03', 'CA-C03']),
        ('CA-S05', '可重载配置提供者', '明确创建、关闭和发布配置的责任', ['CA-P01'])]
    build_project('configargparse', {'title': 'ConfigArgParse配置入口工作场景', 'category': '多来源参数与配置',
        'description': '固定源码上的来源优先级、受限展示、列表语义、布尔取证、格式保真和流式配置重载八项独立只读任务。'}, definitions, scenes, materials,
        branches={'CA-D01': [{'id': 'argument-evidence', 'when': 'The argument definition, parser call and actual CLI/environment/config inputs have not been supplied or declared unavailable, and the answer reasonably requests sufficient evidence.', 'materials': ['disclosure/boolean.md']}]},
        extra_entries={'CA-S03': [{'id': 'diagnose_only', 'task_ids': ['CA-D01']},
            {'id': 'unavailable', 'task_ids': ['CA-D01'], 'materials': ['disclosure/unavailable.md']}]})


if __name__ == '__main__':
    main()
