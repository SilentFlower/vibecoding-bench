"""独立业务验收，只读取当前候选，不联网或调用模型。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
import sys
sys.path.insert(0, str(root / 'library'))
import frontmatter
import json
from frontmatter.default_handlers import JSONHandler
business=True
for value in ({},{'content':'C','handler':'H','nested':{'items':[{'quote':'"}quoted'}]}},{'unicode':'中文'}):
    for indent in (None,0,2):
        body='first\n}\n{"belongs":"to body"}'
        post=frontmatter.loads(json.dumps(value,ensure_ascii=False,indent=indent)+'\n'+body)
        again=frontmatter.loads(frontmatter.dumps(post))
        business &= post.metadata==again.metadata==value and post.content==again.content==body and isinstance(post.handler,JSONHandler)
for bad in ('{bad}','{\n"a": invalid\n}','{\n"a": 1,\n}'):
    try:frontmatter.loads(bad+'\nbody')
    except json.JSONDecodeError:pass
    else:business=False

print(json.dumps({'candidate_import': Path(frontmatter.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
