"""独立业务验收，只读取当前候选，不联网或调用模型。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
import sys
sys.path.insert(0, str(root / 'library'))
import frontmatter
import io
from frontmatter.default_handlers import YAMLHandler,TOMLHandler
business=True
for prefix in ('\n',' \r\n\t\n','   '):
    for handler,text in [(TOMLHandler,'+++\ncontent="C"\nhandler="H"\n+++\nB'),(YAMLHandler,'---\ncontent: C\nhandler: H\n---\nB')]:
        raw=prefix+text
        post=frontmatter.load(io.StringIO(raw))
        restored=frontmatter.loads(frontmatter.dumps(post))
        business &= frontmatter.checks(raw) and isinstance(post.handler,handler) and isinstance(restored.handler,handler)
        business &= post.metadata==restored.metadata=={'content':'C','handler':'H'} and post.content==restored.content=='B'

print(json.dumps({'candidate_import': Path(frontmatter.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
