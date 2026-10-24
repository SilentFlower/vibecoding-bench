"Public regression tests for TRANSITIONS-01-DEV; the complete business contract is in materials/TRANSITIONS-01-DEV-contract.md."
from transitions.extensions.markup import MarkupMachine

class Order:
    "Public regression fixture: Order."
    def __init__(self):self.calls=[]
    def before(self):self.calls.append('before')
    def after(self):self.calls.append('after')

def test_before_after_export_and_actual_roundtrip_execution():
    "Verify before after export and actual roundtrip execution."
    model=Order();machine=MarkupMachine(model=model,states=['draft','packed'],initial='draft',auto_transitions=False,transitions=[['pack','draft','packed']],before_state_change='before',after_state_change='after')
    config=machine.markup
    assert config['before_state_change']==['before'] and config['after_state_change']==['after']
    config={key:value for key,value in config.items() if key!='models'}
    restored=Order();other=MarkupMachine(model=restored,**config)
    assert restored.pack() and restored.calls==['before','after'] and restored.state=='packed'

def test_after_only_and_no_callbacks_are_not_borrowed_from_before():
    "Verify after only and no callbacks are not borrowed from before."
    model=Order();machine=MarkupMachine(model=model,states=['a'],initial='a',auto_transitions=False,after_state_change=['after'])
    assert machine.markup['before_state_change']==[] and machine.markup['after_state_change']==['after']
    assert MarkupMachine(states=['a'],initial='a',auto_transitions=False).markup['after_state_change']==[]

