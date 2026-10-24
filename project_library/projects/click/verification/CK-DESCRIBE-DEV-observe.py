"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import click
_candidate_source_root = root
business = False
try:
    group=click.Group('root');command=click.Command('child');group.add_command(command,name='alias')
    ctx=click.Context(group,info_name='app')
    result=group.describe(ctx)
    child_context=click.Context(command,info_name='alias',parent=ctx)
    business='alias' in result['commands'] and result['usage']==group.get_usage(ctx) and command.describe(child_context)['command_path']=='app alias'

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(click.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
