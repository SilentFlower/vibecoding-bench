"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import tabulate
_candidate_source_root = root
business = False
try:
    from tabulate.accessibility import accessible_html
    from html.parser import HTMLParser
    class Probe(HTMLParser):
        def __init__(self):
            super().__init__();self.tags=[]
        def handle_starttag(self,tag,attrs):
            self.tags.append((tag,dict(attrs)))
    result=accessible_html([['<td>user</td>',5]],headers=['name','value'],caption='A & B',row_headers=True,table_id='orders')
    probe=Probe();probe.feed(result)
    business=(sum(tag=='th' and attrs.get('scope')=='row' for tag,attrs in probe.tags)==1
        and sum(tag=='th' and attrs.get('scope')=='col' for tag,attrs in probe.tags)==2
        and sum(tag=='td' for tag,attrs in probe.tags)==1 and ('table',{'id':'orders'}) in probe.tags)

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(tabulate.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
