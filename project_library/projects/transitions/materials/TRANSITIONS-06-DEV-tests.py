"Public regression tests for TRANSITIONS-06-DEV; the complete business contract is in materials/TRANSITIONS-06-DEV-contract.md."
from transitions import Machine

def test_failed_condition_marks_remaining_skipped_without_transition_callbacks():
    "Verify failed condition marks remaining skipped without transition callbacks."
    seen=[]
    def prepare():seen.append('prepare')
    def false():seen.append('false');return False
    def untouched():seen.append('unreachable');return True
    machine=Machine(states=['draft','packed'],initial='draft',auto_transitions=False,prepare_event=prepare)
    machine.add_transition('pack','draft','packed',conditions=[false,untouched],before=lambda:seen.append('before'))
    report=machine.explain_event(machine,'pack')
    assert not report['allowed'] and [item['status'] for item in report['candidates'][0]['conditions']]==['fail','skipped']
    assert seen==['prepare','false'] and machine.state=='draft'

def test_unless_candidates_success_shortcircuits_and_errors_are_visible():
    "Verify unless candidates success shortcircuits and errors are visible."
    machine=Machine(states=['a','b','c'],initial='a',auto_transitions=False)
    machine.add_transition('go','a','b',unless=lambda:False)
    machine.add_transition('go','a','c',conditions=lambda:(_ for _ in ()).throw(AssertionError('must skip')))
    report=machine.explain_event(machine,'go')
    assert report['allowed'] and report['candidates'][0]['conditions'][0]['target'] is False
    assert report['candidates'][1]['status']=='skipped' and machine.state=='a'
    broken=Machine(states=['a','b'],initial='a',auto_transitions=False)
    broken.add_transition('go','a','b',conditions=lambda:1/0)
    row=broken.explain_event(broken,'go')['candidates'][0]
    assert row['status']=='error' and row['conditions'][0]['error_type']=='ZeroDivisionError'

