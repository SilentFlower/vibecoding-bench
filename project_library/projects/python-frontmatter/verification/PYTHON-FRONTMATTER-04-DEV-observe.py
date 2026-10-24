"""独立业务验收，只读取当前候选，不联网或调用模型。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
import sys
sys.path.insert(0, str(root / 'library'))
import frontmatter
from frontmatter.parsing import parse_result,ParseError
from frontmatter.default_handlers import JSONHandler
business=True
for raw,status in [('plain','absent'),('---\n---\nB','present'),('---\nnull\n---\nB','present'),('---\n42\n---\nB','non_mapping'),('---\n[unclosed\n---\nB','malformed'),('{"a":{"b":1}}\nB','present'),('{"a":bad}\nB','malformed')]:
    result=parse_result(raw,defaults={'seed':1})
    business &= result.status==status and result.metadata.get('seed')==1
    try:strict=parse_result(raw,strict=True)
    except ParseError as error:business &= error.result.status==status and status in ('malformed','non_mapping')
    else:business &= status in ('present','absent')
a=parse_result('{}\nB');b=parse_result('{}\nC');a.metadata['x']=1
business &= 'x' not in b.metadata and isinstance(a.handler,JSONHandler) and b.content=='C'

print(json.dumps({'candidate_import': Path(frontmatter.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
