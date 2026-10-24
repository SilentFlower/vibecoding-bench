"""真实CLI组件加载失败必须让流水线收到非零退出码。"""
import subprocess,sys,os

def run(arguments,source='Title\n=====\n\nBody',cwd=None):
    """执行真实模块入口并禁用用户配置搜索。@return CompletedProcess。"""
    return subprocess.run([sys.executable,'-m','docutils',*arguments],input=source,text=True,capture_output=True,cwd=cwd,env=dict(os.environ,DOCUTILSCONFIG=''),timeout=10)

def test_unknown_writer_nonzero_stderr_only_and_no_target_file(tmp_path):
    """失败既不打印伪输出也不创建目标产物。@return None。"""
    target=tmp_path/'not-created.html';result=run(['--writer=missing_engineering_writer',str(tmp_path/'missing.rst'),str(target)],cwd=tmp_path)
    assert result.returncode!=0 and result.stdout=='' and 'missing_engineering_writer' in result.stderr and not target.exists()

def test_unknown_reader_parser_and_traceback_preserve_diagnostics():
    """三个组件错误均非零，显式traceback仍保留原堆栈。@return None。"""
    for option in ['reader','parser','writer']:
        result=run(['--'+option+'=missing_component']);assert result.returncode!=0 and not result.stdout
    traced=run(['--writer=missing_component','--traceback'])
    assert traced.returncode!=0 and 'Traceback' in traced.stderr and traced.stdout==''

def test_normal_html_still_succeeds_without_changing_published_document():
    """合法writer仍输出真实完整HTML且退出成功。@return None。"""
    result=run(['--writer=html5'])
    assert result.returncode==0 and '<html' in result.stdout and 'Body' in result.stdout
