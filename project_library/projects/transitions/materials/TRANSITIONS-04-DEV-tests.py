"""结构预览不能为了按钮状态执行prepare或guard。"""
from transitions import Machine

def test_preview_metadata_has_no_callback_or_property_side_effect():
    """路径可读但runnable未知，状态和计数完全不动。@return None。"""
    class Order:
        """所有实际执行都会留下计数。"""
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
    """已解析通配事件按当前状态展示，内部目标None保持。@return None。"""
    machine=Machine(states=['a','b'],initial='a',auto_transitions=False)
    machine.add_transition('check','a',None);machine.add_transition('check','a','=')
    assert [item['dest'] for item in machine.preview_event(machine,'check')['candidates']]==[None,'a']
    assert machine.preview_event(machine,'absent')['candidates']==[] and machine.state=='a'

