"""完整执行旧冻结回归，仅稳定一百九十个fixture的临时路径标签。"""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys

root=Path(__file__).parent
settings=json.loads((root/'HTML2TEXT-O01-DEV-node-identities.json').read_text())
source=root/'native_regression.py'
assert hashlib.sha256(source.read_bytes()).hexdigest()==settings['original_runner_sha256']
contract=Path(sys.argv[sys.argv.index('--contract')+1])
assert hashlib.sha256(contract.read_bytes()).hexdigest()==settings['original_contract_sha256']
specification=importlib.util.spec_from_file_location('frozen_html2text_regression',source)
original=importlib.util.module_from_spec(specification);specification.loader.exec_module(original)
copy_original=original.shutil.copyfile
hook='\n\nfrom types import CodeType as _BenchHTMLCode, FunctionType as _BenchHTMLFunction\nimport hashlib as _bench_html_hashlib\n\n_bench_html_original_collection=pytest_collection_modifyitems\n\n\ndef _bench_html_code_digest(code):\n    """核对固定生成器真实代码。@param code 原生成器代码。@return 稳定摘要。"""\n    data={\'bytecode\':code.co_code.hex(),\'constants\':code.co_consts,\'names\':code.co_names,\n          \'variables\':code.co_varnames,\'arguments\':code.co_argcount,\n          \'positional_only\':code.co_posonlyargcount,\'keyword_only\':code.co_kwonlyargcount,\'flags\':code.co_flags}\n    return _bench_html_hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()\n\n\ndef pytest_collection_modifyitems(session,config,items):\n    """按真实fixture和固定参数恢复原标签，原节点与结果仍逐项比较。\n\n    @param session 原pytest会话。@param config 原pytest配置。@param items 全部原测试节点。\n    @return 原冻结控制器结果；原196用例必须全部保留。\n    """\n    state=_state();control=state[\'control\']\n    settings=json.loads(Path(\'/request-data/verification/HTML2TEXT-O01-DEV-node-identities.json\').read_text())\n    source=(Path(control[\'project\'])/settings[\'source_test\']).resolve()\n    assert _bench_html_hashlib.sha256(source.read_bytes()).hexdigest()==settings[\'source_test_sha256\']\n    families=settings[\'families\'];selected=[item for item in items if item.nodeid.split(\'[\',1)[0] in families]\n    assert len(selected)==190\n    module=selected[0].module\n    assert Path(module.__file__).resolve()==source and all(item.module is module for item in selected)\n    tree=ast.parse(source.read_text());pending=[compile(tree,str(source),\'exec\',dont_inherit=True)];codes=[]\n    while pending:\n        parent=pending.pop()\n        for value in parent.co_consts:\n            if isinstance(value,_BenchHTMLCode):codes.append(value);pending.append(value)\n    for name in settings[\'generator_functions\']:\n        actual=getattr(module,name);expected=[code for code in codes if code.co_name==name]\n        assert isinstance(actual,_BenchHTMLFunction) and len(expected)==1\n        assert actual.__code__.co_firstlineno==expected[0].co_firstlineno\n        assert _bench_html_code_digest(actual.__code__)==_bench_html_code_digest(expected[0])\n    expected={(entry[\'function\'],entry[\'fixture\']):entry for entry in settings[\'nodes\']}\n    assert len(expected)==190 and {entry[\'frozen_id\'] for entry in expected.values()}.issubset(set(control[\'required_nodes\']))\n    rows=[];seen=set()\n    for item in selected:\n        prefix=item.nodeid.split(\'[\',1)[0];function=prefix.rsplit(\'::\',1)[1]\n        params=item.callspec.params;filename=params[\'fn\'];assert type(filename) is str\n        fixture=Path(filename).name;key=(function,fixture);assert key in expected and key not in seen;seen.add(key)\n        entry=expected[key];actual_path=Path(filename).resolve()\n        assert actual_path==source.parent/fixture\n        assert _bench_html_hashlib.sha256(actual_path.read_bytes()).hexdigest()==entry[\'html_sha256\']\n        assert _bench_html_hashlib.sha256(actual_path.with_suffix(\'.md\').read_bytes()).hexdigest()==entry[\'markdown_sha256\']\n        argument=families[prefix];actual=params[argument]\n        assert type(actual) is type(entry[\'arguments\'])\n        assert json.dumps(actual,sort_keys=True)==json.dumps(entry[\'arguments\'],sort_keys=True)\n        original=item.nodeid\n        assert re.fullmatch(re.escape(prefix+\'[\'+filename+\'-\'+argument)+r\'\\d+\\]\',original)\n        # fn与参数对象原样执行；只恢复原contract中不影响输入的scratch路径及展示序号。\n        item._nodeid=entry[\'frozen_id\']\n        rows.append({\'function\':function,\'fixture\':fixture,\'actual_id\':original,\'frozen_id\':item.nodeid,\n            \'argument_name\':argument,\'arguments\':actual,\'pytest_indices\':dict(item.callspec.indices),\n            \'html_sha256\':entry[\'html_sha256\'],\'markdown_sha256\':entry[\'markdown_sha256\']})\n    assert len(rows)==190 and seen==set(expected)\n    result=_bench_html_original_collection(session,config,items)\n    evidence={\'status\':\'passed\',\'normalized_node_count\':190,\'source_test_sha256\':settings[\'source_test_sha256\'],\n        \'all_original_inputs_preserved\':True,\'nodes\':sorted(rows,key=lambda row:(row[\'function\'],row[\'fixture\']))}\n    Path(control[\'evidence\'],\'HTML2TEXT-O01-DEV-node-identities.json\').write_text(json.dumps(evidence,sort_keys=True))\n    return result\n'


def copy_with_identity_binding(source_path,destination,*args,**kwargs):
    """仅补充可信临时collector。@param source_path 固定来源。@param destination 临时控制器。
    @param args 原位置参数。@param kwargs 原命名参数。@return 原复制结果。
    """
    result=copy_original(source_path,destination,*args,**kwargs)
    path=Path(destination)
    if path.name=='_bench_native_regression_control.py':
        with path.open('a') as output:output.write(hook)
    return result


original.shutil.copyfile=copy_with_identity_binding
captured=io.StringIO();code=0
try:
    with contextlib.redirect_stdout(captured):original.main()
except SystemExit as outcome:
    code=outcome.code or 0
finally:
    original.shutil.copyfile=copy_original
result=json.loads(captured.getvalue())
evidence=Path(sys.argv[sys.argv.index('--evidence-dir')+1])/'HTML2TEXT-O01-DEV-node-identities.json'
identities=json.loads(evidence.read_text()) if evidence.is_file() else {'status':'not_executed'}
result['controlled_parameter_identities']=identities
if identities.get('status')!='passed' or identities.get('normalized_node_count')!=190:
    result['status']='failed'
print(json.dumps(result,ensure_ascii=False))
raise SystemExit(0 if result['status']=='passed' and code==0 else 1)
