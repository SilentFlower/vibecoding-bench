"""独立业务验收，只读取当前候选，不联网或调用模型。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
from contextlib import ExitStack
from importlib.util import module_from_spec, spec_from_file_location
spec = spec_from_file_location('frozen_native_control', Path(__file__).with_name('native_regression.py'))
control = module_from_spec(spec)
spec.loader.exec_module(control)
cleanup = ExitStack()
suite = control.SUITES['python-markdown']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import markdown
business=True
for config in ({'unlisted_attribute':'data-toc-unlisted'},{'unlisted_attribute':'custom-hide','remove_unlisted_attribute':False}):
    attribute=config['unlisted_attribute']
    md=markdown.Markdown(extensions=['markdown.extensions.toc','markdown.extensions.attr_list'],extension_configs={'markdown.extensions.toc':config})
    output=md.convert('# A\n\n## B {'+attribute+' data-toc-label="Other"}\n\n### C\n\n## D')
    names=[]
    def visit(tokens):
        """收集真实目录层级名。@param tokens 目录。@return None。"""
        for token in tokens:names.append(token['name']);visit(token['children'])
    visit(md.toc_tokens)
    business &= names==['A','C','D'] and 'id="b"' in output
    business &= (attribute in output)==(config.get('remove_unlisted_attribute') is False)

print(json.dumps({'candidate_import': Path(markdown.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
