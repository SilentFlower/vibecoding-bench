"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import box
import io
import json
business = False
try:
    rows = box.BoxList([{'v': [1, 2]}, {'unicode': '界'}, None])
    output = list(rows.iter_jsonl(ensure_ascii=False))
    business = [json.loads(line) for line in output] == rows.to_list() and all(line.endswith('\n') and line.count('\n') == 1 for line in output)
    target = io.StringIO()
    business &= rows.write_jsonl(target) == 3 and not target.closed
    try:
        list(rows.iter_jsonl(indent=2))
    except ValueError:
        pass
    else:
        business = False
    def failing():
        """读取第二条前必须已经可取得首条。@return 迭代器。"""
        yield {'first': True}
        raise RuntimeError('tail')
    stream = box.BoxList.iter_jsonl_records(failing())
    business &= json.loads(next(stream)) == {'first': True}
    stream.close()
except AttributeError:
    business = False

print(json.dumps({'candidate_import': Path(box.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
