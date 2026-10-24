"""区域上下文在同线程异步交错、嵌套和异常中隔离。"""
import asyncio
import humanize
from humanize import i18n
import pytest
def catalog(root,word):
    """构造合成GNU消息目录，供实际gettext读取。@return 根路径。"""
    import struct
    entries={'':'Content-Type: text/plain; charset=UTF-8\nLanguage: xx\nPlural-Forms: nplurals=2; plural=(n != 1);\n','one':word,'%s and %s':'%s et %s'}
    pairs=sorted((key.encode(),value.encode()) for key,value in entries.items());count=len(pairs)
    ids=b'\0'.join(key for key,value in pairs)+b'\0';values=b'\0'.join(value for key,value in pairs)+b'\0'
    head=28;id_start=head+count*16;value_start=id_start+len(ids);out=struct.pack('<7I',0x950412de,0,count,head,head+count*8,0,0)
    offset=0
    for key,value in pairs:out+=struct.pack('<2I',len(key),id_start+offset);offset+=len(key)+1
    offset=0
    for key,value in pairs:out+=struct.pack('<2I',len(value),value_start+offset);offset+=len(value)+1
    target=root/'xx'/'LC_MESSAGES'/'humanize.mo';target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(out+ids+values)
    return root

def test_event_coordinated_tasks_do_not_share_context(tmp_path):
    """两个任务确定交错后仍保留各自真实GNU翻译。@return None。"""
    from humanize.context import locale_scope
    first=catalog(tmp_path/'one','uno');second=catalog(tmp_path/'two','dos')
    async def run():
        ready,other=asyncio.Event(),asyncio.Event()
        async def a():
            with locale_scope('xx',first):
                ready.set();await other.wait();return humanize.apnumber(1)
        async def b():
            await ready.wait()
            with locale_scope('xx',second):
                other.set();await asyncio.sleep(0);return humanize.apnumber(1)
        return await asyncio.gather(a(),b())
    assert asyncio.run(run())==['uno','dos'] and humanize.apnumber(1)=='one'

def test_nested_default_and_exception_restore(tmp_path):
    """嵌套英语作用域覆盖已激活区域，异常退出恢复外层。@return None。"""
    from humanize.context import locale_scope
    root=catalog(tmp_path/'one','uno')
    with locale_scope('xx',root):
        assert humanize.apnumber(1)=='uno'
        with pytest.raises(RuntimeError):
            with locale_scope(None):
                assert humanize.apnumber(1)=='one';raise RuntimeError('app')
        assert humanize.apnumber(1)=='uno'
    assert humanize.apnumber(1)=='one'

def test_manual_thread_state_hidden_and_reentry(tmp_path):
    """手工activate不污染当前scope，同实例重复进入拒绝。@return None。"""
    from humanize.context import locale_scope
    root=catalog(tmp_path/'one','uno');scope=locale_scope('xx',root)
    try:
        with scope:
            i18n.deactivate();assert humanize.apnumber(1)=='uno'
            with pytest.raises(RuntimeError):scope.__enter__()
        with scope:assert humanize.apnumber(1)=='uno'
    finally:i18n.deactivate()
