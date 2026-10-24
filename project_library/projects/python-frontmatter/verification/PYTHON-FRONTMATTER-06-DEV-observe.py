"""独立业务验收，只读取当前候选，不联网或调用模型。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
import sys
sys.path.insert(0, str(root / 'library'))
import frontmatter
import tempfile
from pathlib import Path
from unittest.mock import patch
from frontmatter.atomic import atomic_update,UpdateConflict
business=True
with tempfile.TemporaryDirectory() as temporary:
    path=Path(temporary)/'doc.md';link=Path(temporary)/'link.md'
    raw=b'{"content":"meta","nested":{"x":1}}\nbody';path.write_bytes(raw)
    def change(post):
        """完整业务转换。@param post 原文档。@return 新文档。"""
        post['nested']['x']=2;post.content='new';return post
    atomic_update(path,change)
    loaded=frontmatter.load(path)
    business &= loaded.metadata=={'content':'meta','nested':{'x':2}} and loaded.content=='new' and isinstance(loaded.handler,frontmatter.JSONHandler)
    saved=path.read_bytes()
    for operation in ('replace','fsync'):
        with patch('frontmatter.atomic.os.'+operation,side_effect=OSError('simulated IO failure')):
            try:atomic_update(path,change)
            except OSError:pass
            else:business=False
        business &= path.read_bytes()==saved and sorted(item.name for item in path.parent.iterdir())==['doc.md']
    link.symlink_to(path)
    try:atomic_update(link,change)
    except ValueError:pass
    else:business=False
    business &= link.is_symlink() and path.read_bytes()==saved

print(json.dumps({'candidate_import': Path(frontmatter.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
