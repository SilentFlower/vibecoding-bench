"""完整原生回归只规范六个StringIO地址，结果全量比较后无损压缩输出。"""
import base64
import gzip
import hashlib
import json
import re
from importlib.util import module_from_spec,spec_from_file_location
from pathlib import Path

spec=spec_from_file_location('frozen_pyparsing_control',Path(__file__).with_name('native_regression.py'))
control=module_from_spec(spec);spec.loader.exec_module(control)
original_subtests=control._subtest_results
scopes=(('tests/test_unit.py::Test02_WithoutPackrat::testParseFile', 1, 'call'), ('tests/test_unit.py::Test04_WithPackrat::testParseFile', 1, 'call'), ('tests/test_unit.py::Test06_WithBoundedPackrat::testParseFile', 1, 'call'), ('tests/test_unit.py::Test08_WithUnboundedPackrat::testParseFile', 1, 'call'), ('tests/test_unit.py::Test09_WithLeftRecursionParsing::testParseFile', 1, 'call'), ('tests/test_unit.py::Test10_WithLeftRecursionParsingBoundedMemo::testParseFile', 1, 'call'))
stringio=re.compile(r'<_io\.StringIO object at 0x[0-9a-fA-F]+>')

def normalized(reports,node_ids):
    """只改六个指定参数repr中的地址。@param reports 原报告。@param node_ids 原节点。@return 同序完整子项。"""
    result=original_subtests(reports,node_ids)
    changed=0
    for item in result:
        if (item['parent_nodeid'],item['ordinal'],item['when']) in scopes:
            value=item['context']['kwargs']['input_file']
            if not stringio.fullmatch(value):raise ValueError('冻结StringIO参数展示形式改变')
            item['context']['kwargs']['input_file']='<_io.StringIO object at <address>>'
            changed+=1
    if changed!=len(scopes):raise ValueError('冻结StringIO子项集合改变')
    return result

control._subtest_results=normalized
original_run=control._run

def archived_run(options):
    """原控制全量核验后保留完整可恢复档案。@param options 原参数。@return 保留全部字段的有界结果。"""
    result=original_run(options)
    if 'subtests' not in result:return result
    result=dict(result);items=result.pop('subtests')
    raw=json.dumps(items,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
    compressed=gzip.compress(raw,mtime=0)
    result['subtests_archive']={'encoding':'canonical-json+gzip+base64','count':len(items),
        'raw_bytes':len(raw),'raw_sha256':hashlib.sha256(raw).hexdigest(),
        'gzip_bytes':len(compressed),'gzip_sha256':hashlib.sha256(compressed).hexdigest(),
        'data':base64.b64encode(compressed).decode('ascii')}
    result['subtests_digest']=hashlib.sha256(raw).hexdigest()
    # 六个累计前缀也必须可用原有4MiB文档协议审查；全量归档不丢任何节点、顺序或结果。
    if len(json.dumps(result,ensure_ascii=False,allow_nan=False).encode('utf-8'))>1024*1024:
        raise ValueError('完整子项无损档案超过安全输出预算')
    return result

control._run=archived_run
if __name__=='__main__':control.main()
