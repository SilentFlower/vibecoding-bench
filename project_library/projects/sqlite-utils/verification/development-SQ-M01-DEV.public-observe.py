"""执行旧目标原参考交付的真实公开测试节点，不替换原测试。"""
import json,os,sys,subprocess,tempfile
from pathlib import Path
from xml.etree.ElementTree import parse
root=Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
from contextlib import ExitStack
from importlib.util import module_from_spec, spec_from_file_location
spec = spec_from_file_location('frozen_native_control', Path(__file__).with_name('native_regression.py'))
control = module_from_spec(spec)
spec.loader.exec_module(control)
cleanup = ExitStack()
suite = control.SUITES['sqlite-utils']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup)
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))

with tempfile.TemporaryDirectory() as directory:
    report=Path(directory)/'public.xml'
    run=subprocess.run([sys.executable,'-m','pytest','-q',*['tests/test_fts.py::test_finite_one_shot_columns_preserve_fts'],'--junitxml='+str(report)],cwd=root/'library',env=dict(os.environ,PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'),capture_output=True,timeout=60)
    cases=list(parse(report).getroot().iter('testcase')) if report.exists() else []
    failures=sum(bool(case.findall('failure') or case.findall('error') or case.findall('skipped')) for case in cases)
    print(json.dumps({'passed':run.returncode==0 and len(cases)==4 and failures==0,'executed':len(cases),'failures':failures}))
