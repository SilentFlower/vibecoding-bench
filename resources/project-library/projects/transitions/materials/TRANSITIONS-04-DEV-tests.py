"Public regression tests for TRANSITIONS-04-DEV; the complete business contract is in materials/TRANSITIONS-04-DEV-contract.md."
from transitions import Machine

def test_preview_metadata_has_no_callback_or_property_side_effect():
    "Verify preview metadata has no callback or property side effect."
    class Order:
        "Public regression fixture: Order."
        def __init__(self):self.calls=[]
        def prepare(self):self.calls.append('prepare')
        def guard(self):self.calls.append('guard');return True
    model=Order();machine=Machine(model=model,states=['draft','packed'],initial='draft',auto_transitions=False,prepare_event='prepare')
    machine.add_transition('pack','draft','packed',conditions='guard',prepare='prepare')
    report=machine.preview_event(model,'pack')
    assert report['runnable']=='unknown' and report['candidates'][0]['dest']=='packed'
    assert report['candidates'][0]['conditions']==[{'index':0,'callback':'guard','target':True}]
    assert model.calls==[] and model.state=='draft'

def test_internal_reflexive_multiple_and_unknown_trigger():
    "Verify internal reflexive multiple and unknown trigger."
    machine=Machine(states=['a','b'],initial='a',auto_transitions=False)
    machine.add_transition('check','a',None);machine.add_transition('check','a','=')
    assert [item['dest'] for item in machine.preview_event(machine,'check')['candidates']]==[None,'a']
    assert machine.preview_event(machine,'absent')['candidates']==[] and machine.state=='a'

