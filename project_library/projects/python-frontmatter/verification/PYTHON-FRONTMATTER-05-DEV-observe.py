"""独立业务验收，只读取当前候选，不联网或调用模型。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
import sys
sys.path.insert(0, str(root / 'library'))
import frontmatter
import io
import tempfile
from pathlib import Path
business=True
for encoding in ('utf-8','utf-16-le','gb18030'):
    for text in (' \n+++\ncontent="中文"\nhandler="H"\n+++\nB','{"content":"中文","handler":"H"}\nB'):
        stream=io.BytesIO(text.encode(encoding));post=frontmatter.load(stream,encoding=encoding)
        out=io.BytesIO();frontmatter.dump(post,out,encoding=encoding,ensure_ascii=False) if isinstance(post.handler,frontmatter.JSONHandler) else frontmatter.dump(post,out,encoding=encoding)
        out.seek(0);again=frontmatter.load(out,encoding=encoding)
        business &= not stream.closed and not out.closed and post.metadata==again.metadata and post.content==again.content=='B'
with tempfile.TemporaryDirectory() as temporary:
    path=Path(temporary)/'text.md';post=frontmatter.Post('中文',title='名字')
    frontmatter.dump(post,path,encoding='utf-16-le');business &= frontmatter.load(path,encoding='utf-16-le').content=='中文'

print(json.dumps({'candidate_import': Path(frontmatter.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
