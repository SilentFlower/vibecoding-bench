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
    machine=Flow();runner=MachineRunner(machine);first=runner.dispatch('advance',index=4);second=runner.dispatch('reset',index=5)
    business=first.index==4 and second.before.states==('ready',) and second.after.states==('draft',) and tuple(machine.configuration_values)==('draft',)

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
