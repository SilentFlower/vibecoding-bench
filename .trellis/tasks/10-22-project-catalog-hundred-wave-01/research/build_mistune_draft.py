"""制作真实文档配置、AST、空文档修复和Markdown重排任务。"""
from draft_content import build_project


def main() -> None:
    """生成四场景八项Mistune独立任务。@return None。"""
    materials = {
        'materials/document.md': 'A ~~old~~ item.\n\n<b>商品</b>\n\n| Name | Qty |\n|---|---|\n|coffee|2|\n',
        'materials/entry-comparison.py': '''import mistune

text = open("document.md", encoding="utf-8").read()
print(mistune.markdown(text))
print(mistune.html(text))
''',
        'materials/document-plan.md': 'A local document conversion workflow needs table and strikethrough syntax with an explicit raw-HTML/escaping policy. Choose a reusable parser configuration, a renderer and a per-document state boundary, and validate representative outputs. Keep local HTML publishing and editor/indexer AST needs explicit. Do not assume arbitrary concurrent use of mutable custom plugins/renderers is guaranteed safe, or that reformatting preserves original source bytes. No service or library patch is required for this planning task.\n',
        'materials/ast-api.py': '''import json
import mistune

tokens = mistune.markdown("# 咖啡\\n\\nCoffee **beans**.", renderer="ast")
print(type(tokens))
print(json.dumps(tokens, ensure_ascii=False))
''',
        'materials/ast-cli.md': 'The actual candidate command python -m mistune -r ast -m "# 咖啡" reaches an assertion that the renderer result is a string. The Python API can return structured tokens. The application needs local JSON for an editor/indexer; propose a compatible API-based export without claiming that the existing CLI already serializes AST JSON or delivering an unauthorized CLI feature.\n',
        'materials/empty-cases.md': 'Compare the real candidate CLI with an empty stdin pipe; explicit -m ""; -f <zero-byte-file>; -m "" -o <new-output-file>; and -m "" -f <file-containing-a-heading>. Also compare -m 0, a missing file, and a real interactive TTY with no arguments. The API accepts an empty document. In the pinned CLI the first two cases report a missing message while the zero-byte file succeeds. All paths and data must be local and synthetic.\n',
        'materials/empty-contract.md': 'Treat empty piped stdin and explicit -m "" as provided valid empty documents: exit 0 and use the ordinary renderer/output path. With -o, create an actual empty result file. Explicit -m, including an empty string, takes precedence over -f. Preserve existing nonempty messages/files, text 0 and missing-file failure. A real interactive TTY with no message/file still reports missing input and exits nonzero immediately, without blocking for input. Do not add AST JSON serialization, change default plugins/renderers, alter other output policy or test controls. Only library/src/mistune/__main__.py and library/tests/test_cli.py may change. Add meaningful original-failing public tests; preserve the complete frozen original main/subtest suite.\n',
        'materials/normalize-markdown.py': '''from mistune import create_markdown, markdown
from mistune.renderers.markdown import MarkdownRenderer

source = "Coffee __beans__.\\n"
rewritten = create_markdown(renderer=MarkdownRenderer())(source)
print(repr(source), repr(rewritten))
print(markdown(source) == markdown(rewritten))
'''}
    definitions = [
        ('MS-U01', 'understand', '解释快捷HTML入口和默认Markdown入口',
            'Trace the supplied document through mistune.markdown and mistune.html. Explain observed raw HTML escaping and table/strikethrough behavior from their actual defaults. Do not edit files.',
            ['materials/document.md', 'materials/entry-comparison.py'], 'explained',
            'Explain the actual different escape/plugin defaults: markdown defaults to escaping with no chosen plugins, while html is preconfigured with escape=False and strikethrough/footnotes/table. Do not treat the two conveniences as identical.', ['different_entry_defaults_observed']),
        ('MS-C01', 'consult', '用已有工厂明确文档插件与HTML策略',
            'Recommend an explicit existing parser configuration for the supplied table/strikethrough document and chosen literal HTML policy. Explain how create_markdown resolves plugins and renderer choices, and decide whether the library needs a patch.',
            ['materials/document.md', 'materials/entry-comparison.py', 'materials/document-plan.md'], 'advice_no_code_change',
            'Use the real create_markdown API with explicit escape and plugin selections rather than relying on mismatched convenience defaults. Existing APIs meet the stated syntax/configuration need without a library modification.', ['existing_explicit_configuration']),
        ('MS-P01', 'plan', '规划可复用的本地文档转换配置',
            'Plan the supplied local document workflow with explicit syntax plugins, renderer, HTML policy, per-document state and representative regression fixtures. Separate publishing and AST consumers and state reuse/concurrency boundaries. Do not implement changes.',
            ['materials/document.md', 'materials/document-plan.md'], 'viable_plan_no_library_change',
            'Give a workable existing-API configuration/reuse plan, fresh per-document state and meaningful output validation. Do not promise arbitrary custom plugin thread safety or byte-perfect Markdown rewriting, and do not introduce an unnecessary service or parser API.', ['existing_explicit_configuration', 'sequential_document_state_distinct']),
        ('MS-U02', 'understand', '解释结构化AST与JSON序列化边界',
            'Trace the supplied AST API call. Explain the returned Python structure, its purpose versus rendered HTML, and the explicit serialization step needed for JSON text. Do not edit files or assume every renderer returns a string.',
            ['materials/ast-api.py'], 'explained',
            'Explain the actual list of structured tokens from renderer=ast (or renderer=None) and explicit json.dumps conversion. Distinguish Python objects, JSON text and rendered HTML without inventing source-position fields absent from the actual tokens.', ['structured_ast_is_json_serializable']),
        ('MS-C02', 'consult', '为现有CLI的AST限制选择兼容导出',
            'Diagnose the supplied CLI AST assertion at its actual result boundary, then recommend an existing API-based local JSON export for the editor/indexer. Do not modify files or claim an unimplemented CLI feature was delivered.',
            ['materials/ast-api.py', 'materials/ast-cli.md'], 'advice_with_limits',
            'Explain that the current CLI asserts a string even when the AST renderer returns a list. Recommend the existing AST API with explicit JSON serialization and output handling; do not claim the pinned CLI already implements AST JSON export or conflate the failure with invalid Markdown.', ['structured_ast_is_json_serializable', 'cli_ast_not_serialized_original']),
        ('MS-D01', 'diagnose', '定位空文档和未提供输入的混淆',
            'Use the complete supplied CLI cases. Explain why empty piped stdin and explicit empty -m are rejected while the API and zero-byte file accept an empty document. Locate the actual dispatch condition and preserve the successful controls. Do not edit files.',
            ['materials/empty-cases.md'], 'diagnosed',
            'Ground the diagnosis in message truthiness conflating empty strings with absence and the separate file branch. The parsing API accepts empty documents; do not label an empty document malformed or blame unrelated plugins.', ['original_empty_dispatch_gap', 'api_empty_document_valid']),
        ('MS-M01', 'modify', '修复空文档CLI并保留真实输出副作用',
            'Implement the complete public empty-document CLI contract, including actual -o file creation, explicit empty-message precedence and nonblocking interactive absence. Preserve nonempty/missing-file behavior and modify only the authorized implementation/test files with meaningful original-failing public tests.',
            ['materials/empty-cases.md', 'materials/empty-contract.md'], 'implemented',
            'Distinguish None from provided empty text and pass valid empty documents through the normal renderer/output path. Satisfy pipe/message/file/priority/PTY controls without adding AST JSON features or changing plugins/controls; complete frozen original regression and public tests must pass.', ['pipe_and_message_empty_valid', 'empty_file_preserved', 'explicit_empty_output_file_written', 'explicit_empty_message_has_priority', 'nonempty_and_missing_preserved', 'interactive_absence_does_not_block']),
        ('MS-C03', 'consult', '区分Markdown规范化与原始文本保真',
            'Explain the supplied MarkdownRenderer example and assess whether it meets a byte-for-byte source-preservation requirement. Compare actual formatting normalization with retained rendered meaning and recommend an appropriate application boundary without modifying the library.',
            ['materials/normalize-markdown.py'], 'advice_with_limits',
            'Explain the actual __beans__ to **beans** normalization with equal rendered HTML, distinguishing useful reformatting from original-byte preservation. Do not claim all plugin/renderers preserve every semantic extension or promise lexical source fidelity.', ['markdown_renderer_normalizes_source'])]
    scenes = [('MS-S01', '文档语法和渲染配置', '明确快捷入口差异并规划复用', ['MS-U01', 'MS-C01', 'MS-P01']),
        ('MS-S02', '编辑器的结构化文档', '区分AST对象和已有导出边界', ['MS-U02', 'MS-C02']),
        ('MS-S03', '空文档的本地CLI处理', '独立诊断并修复输入存在性判断', ['MS-D01', 'MS-M01']),
        ('MS-S04', 'Markdown重排与保真', '按真实表示能力选择工具边界', ['MS-C03'])]
    build_project('mistune', {'title': 'Mistune文档处理工作场景', 'category': '文档解析与本地转换',
        'description': '固定真实源码上的文档配置、AST、CLI兼容、空输入修复和Markdown重排咨询；四场景八任务。'},
        definitions, scenes, materials,
        modifications={'MS-M01': ['library/src/mistune/__main__.py', 'library/tests/test_cli.py']},
        extra_entries={'MS-S03': [{'id': 'diagnose_only', 'task_ids': ['MS-D01']},
            {'id': 'modify_direct', 'task_ids': ['MS-M01']}]})


if __name__ == '__main__':
    main()
