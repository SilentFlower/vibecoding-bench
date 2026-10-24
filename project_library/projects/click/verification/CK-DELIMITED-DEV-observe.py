"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import click
_candidate_source_root = root
business = False
try:
    from click.delimited import DelimitedList
    from click.testing import CliRunner
    @click.command()
    @click.option('--states',type=DelimitedList(click.Choice(['Ready','Done'],case_sensitive=False),separator=';',min_items=1,max_items=3))
    def command(states):
        click.echo('|'.join(states))
    first=CliRunner().invoke(command,['--states','ready;DONE'])
    second=CliRunner().invoke(command,['--states','ready;unknown'])
    business=first.exit_code==0 and first.output.strip()=='Ready|Done' and second.exit_code==2

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(click.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
