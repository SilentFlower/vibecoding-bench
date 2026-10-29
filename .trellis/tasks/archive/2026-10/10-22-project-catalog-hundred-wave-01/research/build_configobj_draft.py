"""制作已有ConfigObj能力可解决的真实配置校验、编辑和组合场景。"""
from draft_content import build_project


def main() -> None:
    """生成四场景九项独立任务，诊断材料按实际请求披露。@return None。"""
    specification = '[service]\nport = integer(min=1, max=65535)\nenabled = boolean\nrequired = string(min=1)\nworkers = integer(min=1, default=2)\n'
    invalid = '[service]\nport = 0\nenabled = maybe\nextra = spare\n'
    materials = {
        'materials/service.ini': '[service]\nport = 8000\nenabled = false\nrequired = orders\n',
        'materials/service.configspec': specification,
        'materials/default-policy.md': 'Construct separate ConfigObj instances from the supplied line lists and configspec, then validate each with Validator(). Compare ordinary validate with validate(copy=True). Inspect actual port/enabled/workers Python values, section.defaults and write() output without a filename. The application wants the default workers=2 to appear in the generated output, using existing APIs.\n',
        'materials/startup-symptom.md': 'An application says configuration validation failed during startup. The actual configuration, configspec, validator construction, validation call and result have not been supplied. Request sufficient evidence before diagnosing.\n',
        'disclosure/invalid.ini': invalid,
        'disclosure/service.configspec': specification,
        'disclosure/startup-events.md': 'The actual synthetic call is cfg=ConfigObj(config_lines, configspec=spec_lines); result=cfg.validate(Validator(), preserve_errors=True); flatten_errors(cfg,result). No custom checks are registered. The application tested if result and mistakenly treated a nonempty failure mapping as complete success. No further production facts are supplied.\n',
        'disclosure/unavailable.md': 'The actual configuration, configspec, validator construction and validation call/result cannot be provided. There is no further incident reproduction.\n',
        'materials/invalid.ini': invalid,
        'materials/error-events.md': 'Use the supplied invalid configuration and configspec with preserve_errors=True, then flatten_errors. Inspect bool(result), result is True, section paths, missing required values and actual exception types. Separately add extra=spare to the valid configuration and compare get_extra_values before and after validate. Do not read real configuration or environment files.\n',
        'materials/startup-policy.md': 'Plan complete startup configuration publication with explicit configspec/Validator checks and an application policy that rejects unknown keys. Defaults may be inserted and checks may mutate values; failures must prevent publication. Identify when get_extra_values is meaningful, how paths and error types reach diagnostics, and how to avoid treating a nonempty result mapping as success. Do not implement changes.\n',
        'materials/edit.ini': '# bakery\n[service] # heading\n# purchase budget\nlimit    =    2   # units\nlabel = 茶\n',
        'materials/edit-policy.md': 'Parse the supplied synthetic lines with encoding="utf-8", change service.limit to "3" in a separate in-memory experiment, and inspect write() without a filename. Explain original comments and Unicode, returned element types and how a caller can use an appropriate memory/binary output target. No project files may be edited. Is this a general byte-identical text editor?\n',
        'materials/merge.json': '{"base":{"service":{"host":"old-db","port":"8000","labels":["a","b"]}},"override":{"service":{"port":"9000","labels":["c"]}}}\n',
        'materials/interpolation.ini': 'base = /srv\n[service]\nroot = %(base)s/orders\n',
        'materials/composition-events.md': 'Compare recursive merge of the supplied dictionaries with list concatenation expectations. Separately read service.root from the supplied interpolated configuration, set the root base value to /opt in memory, read again, and inspect write(). Only the synthetic in-memory experiment is authorized; do not change files.\n'}
    definitions = [
        ('CO-U01', 'understand', '解释configspec的真实类型转换与默认插入',
            'Trace validation of the supplied service configuration. Give actual Python types/values for port, enabled and missing workers, and explain whether validation merely reports or also mutates successful values. Do not edit files.',
            ['materials/service.ini', 'materials/service.configspec', 'materials/default-policy.md'], 'explained',
            'Successful validation returns the singleton True, converts port to int8000 and enabled to False, and supplies int workers2. Existing ConfigObj validation may update the configuration values; it is not a detached report with no mutation.', ['validation_converts_values_and_adds_default']),
        ('CO-C01', 'consult', '用已有copy选项把默认写入生成配置',
            'Explain why a readable default workers value may be absent from write() output and whether the supplied generated-output requirement needs a library patch. Compare ordinary validate and copy=True with actual defaults state. No files may be changed.',
            ['materials/service.ini', 'materials/service.configspec', 'materials/default-policy.md'], 'advice_no_code_change',
            'Ordinary validation adds workers2 but marks a missing default in section.defaults, so write skips it. On a separate object, validate(copy=True) leaves that generated default as a written value and outputs workers=2. Existing copy behavior satisfies this output need; do not globally alter default writing.', ['ordinary_default_is_readable_but_not_written', 'copy_true_writes_default']),
        ('CO-D01', 'diagnose', '先取配置和校验调用再判断启动失败',
            'Investigate the supplied startup-validation symptom. Request actual configuration, configspec, validator setup and validation call/result or an equivalent reproduction. Diagnose disclosed evidence only, and report the evidence limit if unavailable. Do not edit files.',
            ['materials/startup-symptom.md'], 'diagnosed_no_code_change',
            'Initially request sufficient actual configuration, configspec, validator setup and validation call/result without inventing a failing field or cause. Diagnose only the disclosed validation and application-control evidence, preserve actual error paths/types and limits, and distinguish library behavior from application policy. Unavailable material permits insufficient_information and a concrete evidence plan.', None),
        ('CO-U02', 'understand', '解释嵌套校验错误、缺失值与真值陷阱',
            'Trace the supplied invalid configuration using preserve_errors=True and flatten_errors. Explain exact section/key paths, the difference between missing values and present invalid values, and why if result is an unsafe success test. Do not edit files.',
            ['materials/invalid.ini', 'materials/service.configspec', 'materials/error-events.md'], 'explained',
            'Flattened failures identify service.port as VdtValueTooSmallError, service.enabled as VdtTypeError and missing service.required as False. The failure mapping is nonempty/truthy but is not singleton True; only result is True indicates complete validation success. Do not call missing fields successful or discard paths.', ['flattened_errors_keep_path_and_exception', 'failed_mapping_is_truthy_but_not_true']),
        ('CO-P01', 'plan', '规划完整校验和额外键拒绝后再发布',
            'Plan the supplied startup publication and unknown-key policy using real ConfigObj APIs. Include mutated validated values/defaults, explicit success checks, extra-key timing and structured diagnostics. No implementation is authorized.',
            ['materials/startup-policy.md', 'materials/service.ini', 'materials/service.configspec', 'materials/error-events.md'], 'planned_without_library_change',
            'Validate a private configuration, require result is True, then enforce an explicit extra-key policy using get_extra_values after validation; before validation its empty list proves nothing. Valid extra fields are not automatically rejected by configspec. Publish only a fully accepted configuration, preserving paths/error distinctions in diagnostics.', ['extras_require_prior_validation', 'validation_does_not_reject_extra_keys', 'failed_mapping_is_truthy_but_not_true']),
        ('CO-U03', 'understand', '解释保留注释的内存配置编辑输出',
            'Trace the supplied in-memory limit edit with explicit UTF-8. Explain which comments and Unicode survive, the return shape/types of write() without a filename, and how reparsing the returned content confirms the changed value. Do not edit project files.',
            ['materials/edit.ini', 'materials/edit-policy.md'], 'explained',
            'The head, section, preceding and inline comments survive with label茶 and limit3. With encoding=utf-8 and no filename/output target, write returns a list of bytes lines rather than one str or an already-written file. Reparse with the same encoding to verify logical values.', ['comments_and_unicode_survive_value_edit', 'explicit_encoding_returns_byte_lines']),
        ('CO-C02', 'consult', '选择已有输出接口并明确文本保真边界',
            'Advise how to use the supplied edited configuration in memory or a binary output target with current APIs. Distinguish preserved comments/logical values from a promise of arbitrary byte-identical formatting. No library change or project-file edit is requested.',
            ['materials/edit.ini', 'materials/edit-policy.md'], 'advice_with_limits',
            'Use existing write() line output with correct encoding/newline handling or provide a binary file-like target such as BytesIO because write writes encoded bytes. Preserve comments/values but do not promise arbitrary original spacing or byte-identical formatting, or treat byte lines as a single Unicode string.', ['comments_and_unicode_survive_value_edit', 'explicit_encoding_returns_byte_lines']),
        ('CO-U04', 'understand', '解释配置层递归覆盖和列表替换',
            'Trace merge for the supplied base/override dictionaries. Give retained host, resulting port and labels, and clarify whether list values are recursively appended. Do not edit files.',
            ['materials/merge.json', 'materials/composition-events.md'], 'explained',
            'Section.merge recurses where both existing and incoming values are dictionaries. host stays old-db, port becomes string9000, and labels becomes [c] as an entire replacement. It does not concatenate [a,b] with [c] or provide an undeclared merge strategy.', ['merge_recurses_and_replaces_lists']),
        ('CO-C03', 'consult', '区分读取时插值和保存原始配置表达式',
            'Explain the supplied interpolation reads before/after changing base in memory and the subsequent write output. Does an initial read permanently replace the expression? Recommend an explicit application snapshot boundary without changing files.',
            ['materials/interpolation.ini', 'materials/composition-events.md'], 'advice_with_limits',
            'The reads yield /srv/orders then /opt/orders because existing interpolation resolves against current configuration at access. write temporarily disables interpolation and retains root=%(base)s/orders, then restores behavior. A deliberate application snapshot is separate; do not claim an initial read permanently rewrites raw expressions or supplies environment expansion.', ['interpolation_is_resolved_at_read', 'write_preserves_interpolation_expression'])]
    scenes = [('CO-S01', '类型转换与默认发布', '使用现有校验和copy选项生成有效配置', ['CO-U01', 'CO-C01']),
        ('CO-S02', '应用启动校验取证', '按真实材料处理错误、真值和额外键策略', ['CO-D01', 'CO-U02', 'CO-P01']),
        ('CO-S03', '注释和Unicode编辑输出', '明确已有写出接口和文本保真范围', ['CO-U03', 'CO-C02']),
        ('CO-S04', '配置层组合与插值', '区分递归覆盖、列表替换和动态读取', ['CO-U04', 'CO-C03'])]
    build_project('configobj', {'title': 'ConfigObj应用配置工作场景', 'category': '配置校验与编辑',
        'description': '固定真实源码上的类型默认、启动校验取证、注释输出和配置组合九项独立只读任务。'},
        definitions, scenes, materials,
        branches={'CO-D01': [{'id': 'validation-evidence', 'when': 'The actual configuration, configspec, validator setup and validation call/result have not been disclosed, the conversation does not say they are unavailable, and the answer reasonably requests a sufficient reproduction.',
            'materials': ['disclosure/invalid.ini', 'disclosure/service.configspec', 'disclosure/startup-events.md']}]},
        extra_entries={'CO-S02': [{'id': 'diagnose_only', 'task_ids': ['CO-D01']},
            {'id': 'unavailable', 'task_ids': ['CO-D01'], 'materials': ['disclosure/unavailable.md']}]})


if __name__ == '__main__':
    main()
