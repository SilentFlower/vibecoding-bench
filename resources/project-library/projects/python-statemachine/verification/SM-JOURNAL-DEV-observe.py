"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import statemachine
_candidate_source_root = root
_candidate_import_bound = Path(statemachine.__file__).resolve().is_relative_to(_candidate_source_root / 'library')
business = False
try:
    from statemachine import StateMachine,State

    class Flow(StateMachine):
        draft=State(initial=True)
        ready=State()
        done=State(final=True)
        advance=draft.to(ready)
        finish=ready.to(done)
        reset=ready.to(draft)
    from statemachine.runner import MachineRunner
    from statemachine.journal import dumps_journal,loads_journal
    machine=Flow();rows=list(MachineRunner(machine).run(['advance','reset','advance','finish']))
    restored=loads_journal(dumps_journal(rows))
    business=len(restored)==4 and restored[1].after.states==('draft',) and restored[-1].after.states==('done',) and tuple(machine.configuration_values)==('done',)

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
