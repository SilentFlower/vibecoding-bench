"Public regression tests for DOCUTILS-O01-DEV; the complete business contract is in materials/DOCUTILS-O01-DEV-contract.md."
import subprocess,sys,os

def run(arguments,source='Title\n=====\n\nBody',cwd=None):
    "Support the public regression through run."
    return subprocess.run([sys.executable,'-m','docutils',*arguments],input=source,text=True,capture_output=True,cwd=cwd,env=dict(os.environ,DOCUTILSCONFIG=''),timeout=10)

def test_unknown_writer_nonzero_stderr_only_and_no_target_file(tmp_path):
    "Verify unknown writer nonzero stderr only and no target file."
    target=tmp_path/'not-created.html';result=run(['--writer=missing_engineering_writer',str(tmp_path/'missing.rst'),str(target)],cwd=tmp_path)
    assert result.returncode!=0 and result.stdout=='' and 'missing_engineering_writer' in result.stderr and not target.exists()

def test_unknown_reader_parser_and_traceback_preserve_diagnostics():
    "Verify unknown reader parser and traceback preserve diagnostics."
    for option in ['reader','parser','writer']:
        result=run(['--'+option+'=missing_component']);assert result.returncode!=0 and not result.stdout
    traced=run(['--writer=missing_component','--traceback'])
    assert traced.returncode!=0 and 'Traceback' in traced.stderr and traced.stdout==''

def test_normal_html_still_succeeds_without_changing_published_document():
    "Verify normal html still succeeds without changing published document."
    result=run(['--writer=html5'])
    assert result.returncode==0 and '<html' in result.stdout and 'Body' in result.stdout
