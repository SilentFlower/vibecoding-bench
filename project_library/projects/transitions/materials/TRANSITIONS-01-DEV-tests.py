"""配置往返的before/after回调不能混淆。"""
from transitions.extensions.markup import MarkupMachine

class Order:
    """本地订单业务回调。"""
    def __init__(self):self.calls=[]
    def before(self):self.calls.append('before')
    def after(self):self.calls.append('after')

def test_before_after_export_and_actual_roundtrip_execution():
    """导出并重建后两类回调各执行一次。@return None。"""
    model=Order();machine=MarkupMachine(model=model,states=['draft','packed'],initial='draft',auto_transitions=False,transitions=[['pack','draft','packed']],before_state_change='before',after_state_change='after')
    config=machine.markup
    assert config['before_state_change']==['before'] and config['after_state_change']==['after']
    config={key:value for key,value in config.items() if key!='models'}
    restored=Order();other=MarkupMachine(model=restored,**config)
    assert restored.pack() and restored.calls==['before','after'] and restored.state=='packed'

def test_after_only_and_no_callbacks_are_not_borrowed_from_before():
    """空before不应该造成after丢失。@return None。"""
    model=Order();machine=MarkupMachine(model=model,states=['a'],initial='a',auto_transitions=False,after_state_change=['after'])
    assert machine.markup['before_state_change']==[] and machine.markup['after_state_change']==['after']
    assert MarkupMachine(states=['a'],initial='a',auto_transitions=False).markup['after_state_change']==[]

