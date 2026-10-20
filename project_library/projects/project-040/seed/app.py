"""News Topic Annotation Dashboard 的可运行初始版本，样例均为合成数据。"""
import hashlib
import html
import json
import math
import re
import statistics
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

FIELDS = {'label': 'headline', 'metric': 'mentions', 'group': 'topic', 'state': 'status', 'date': 'date'}


def baseline(items):
    """计算初始业务结果。@param items 业务记录。@return 初始结果。"""
    label, metric, group = FIELDS['label'], FIELDS['metric'], FIELDS['group']
    state, day = FIELDS['state'], FIELDS['date']
    labels = [str(r.get(label, '')) for r in items]
    values = [r.get(metric, 0) for r in items]
    groups = [str(r.get(group, '')) for r in items]
    states = [r.get(state) for r in items]
    days = [r.get(day, '') for r in items]
    return {'topics':{key:sum(v for g,v in zip(groups,values) if g==key) for key in sorted(set(groups))},'articles':len(items)}


def handle(request):
    """处理一条本地 JSON 业务请求。@param request 输入对象。@return 业务结果。"""
    if not isinstance(request, dict):
        return {'error': 'invalid_request'}
    if request.get('action', 'overview') == 'overview':
        return baseline(request.get('items', json.loads(Path(__file__).with_name('demo.json').read_text())))
    return {'error': 'unsupported_action'}


if __name__ == '__main__':
    for line in sys.stdin:
        if line.strip():
            try:
                response = handle(json.loads(line))
                print(json.dumps(response, ensure_ascii=False, allow_nan=False))
            except (ValueError, KeyError, TypeError) as error:
                print(json.dumps({'error': type(error).__name__}))
