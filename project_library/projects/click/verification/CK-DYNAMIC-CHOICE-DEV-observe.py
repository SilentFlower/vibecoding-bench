"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import click
_candidate_source_root = root
business = False
try:
    from click.dynamic import DynamicChoice
    from click.testing import CliRunner
    state={'choices':['Old']};calls=[]
    def provider(ctx):
        calls.append(ctx)
        return iter(state['choices'])
    type_=DynamicChoice(provider,case_sensitive=False)
    first=type_.convert('old',None,None);state['choices']=['New'];second=type_.convert('new',None,None)
    business=first=='Old' and second=='New' and len(calls)==2

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(click.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
