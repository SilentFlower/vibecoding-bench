"""制作调用选项隔离参考、仅内置格式修复反例和原版公开测试控制。"""
from pathlib import Path
from shutil import copytree


WORKSPACE = Path.cwd() / '.deploy/project-catalog-hundred/stage-01'
TESTS = '''

def test_export_call_options_do_not_leak_between_instances(monkeypatch):
    """本次覆盖不得成为下一实例的默认。@param monkeypatch 测试隔离。@return None。"""
    registry = {key: row._replace(formatter_args=dict(row.formatter_args))
        for key, row in TabularOutputFormatter._output_formats.items()}
    monkeypatch.setattr(TabularOutputFormatter, "_output_formats", registry)
    default = registry["simple"].formatter_args["missing_value"]
    first = "\\n".join(TabularOutputFormatter("simple").format_output(
        [[None]], ["value"], missing_value="CALL_ONLY"))
    second = "\\n".join(TabularOutputFormatter("simple").format_output([[None]], ["value"]))
    assert "CALL_ONLY" in first
    assert default in second and "CALL_ONLY" not in second
    assert registry["simple"].formatter_args["missing_value"] == default


def test_registered_export_defaults_and_caller_mapping_stay_unchanged(monkeypatch):
    """自定义格式和注册者默认同样保持。@param monkeypatch 测试隔离。@return None。"""
    monkeypatch.setattr(TabularOutputFormatter, "_output_formats", {})

    def render(data, headers, missing_value="BASE", **kwargs):
        """返回本次缺值策略。@param data 行。@param headers 表头。@param missing_value 缺值。@param kwargs 其他选项。@return 行迭代器。"""
        return iter([missing_value])

    defaults = {"missing_value": "BASE"}
    TabularOutputFormatter.register_new_formatter("custom_export", render, kwargs=defaults)
    first = list(TabularOutputFormatter("custom_export").format_output(
        [[None]], ["value"], missing_value="CUSTOM"))
    second = list(TabularOutputFormatter("custom_export").format_output([[None]], ["value"]))
    assert first == ["CUSTOM"]
    assert second == ["BASE"]
    assert defaults == {"missing_value": "BASE"}
'''


def main() -> None:
    """仅在两个授权文件上形成独立参考差异。@return None。"""
    seed = WORKSPACE / 'drafts/projects/cli-helpers/seed'
    reference = WORKSPACE / 'references/cli-helpers'
    control = WORKSPACE / 'public-test-controls/cli-helpers-original'
    wrong = WORKSPACE / 'wrong-candidates/cli-helpers-builtins-only'
    for path in (reference, control, wrong):
        if path.exists():
            raise ValueError('参考和控制不允许覆盖')
    copytree(seed, reference)
    module = reference / 'library/cli_helpers/tabular_output/output_formatter.py'
    original = module.read_text(encoding='utf-8')
    anchor = '        fkwargs.update(kwargs)\n'
    if original.count(anchor) != 1:
        raise ValueError('默认覆盖锚点与已读源码不一致')
    enhanced = original.replace(anchor,
        '        # 注册默认属于所有实例，本次覆盖必须使用独立顶层映射。\n'
        '        fkwargs = dict(fkwargs)\n' + anchor)
    module.write_text(enhanced, encoding='utf-8')
    tests = reference / 'library/tests/tabular_output/test_output_formatter.py'
    tests.write_text(tests.read_text(encoding='utf-8') + TESTS, encoding='utf-8')
    copytree(seed, control)
    (control / 'library/tests/tabular_output/test_output_formatter.py').write_text(tests.read_text(encoding='utf-8'), encoding='utf-8')
    copytree(reference, wrong)
    (wrong / 'library/cli_helpers/tabular_output/output_formatter.py').write_text(original.replace(anchor,
        '        if format_name == "simple":\n            fkwargs = dict(fkwargs)\n' + anchor), encoding='utf-8')
    print('CLI Helpers参考、两条公开测试、原版控制和仅内置格式修复反例已制作。')


if __name__ == '__main__':
    main()
