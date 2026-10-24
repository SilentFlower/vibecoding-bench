"""公开CLI AST结构化交付回归。"""
import json
import subprocess
import sys

def run(*args,input=''):
    return subprocess.run([sys.executable,'-m','mistune',*args],input=input,text=True,capture_output=True,timeout=8)

def test_message_ast_is_actual_nested_json():
    result=run('-r','ast','-m','# Title\n\nHello **world**')
    tokens=json.loads(result.stdout)
    assert result.returncode==0 and tokens[0]['type']=='heading'
    assert any(child['type']=='strong' for token in tokens for child in token.get('children',[]))

def test_empty_explicit_and_piped_input_export_empty_arrays():
    for args in (('-r','ast','-m',''),('-r','ast')):
        result=run(*args)
        assert result.returncode==0 and json.loads(result.stdout)==[]

def test_file_output_is_utf8_json_without_stdout(tmp_path):
    source=tmp_path/'in.md';source.write_text('# 雪\n');target=tmp_path/'out.json'
    result=run('-r','ast','-f',str(source),'-o',str(target))
    assert result.returncode==0 and result.stdout=='' and json.loads(target.read_text())[0]['children'][0]['raw']=='雪'

def test_html_mode_is_still_plain_html():
    result=run('-m','**value**')
    assert result.returncode==0 and '<strong>value</strong>' in result.stdout
