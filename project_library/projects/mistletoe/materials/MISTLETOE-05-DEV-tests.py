"""显式破折号将stdin作为一份文档消费并正常退出。"""
import os
import subprocess
import sys
import unittest
from mistletoe import cli, HtmlRenderer


def test_utf8_pipe_converts_once():
    """批处理输出只有HTML，无REPL提示。@return None。"""
    result=subprocess.run([sys.executable,'-m','mistletoe','-'],input='# 中文标题\n',text=True,capture_output=True,timeout=3)
    assert result.returncode==0 and result.stdout=='<h1>中文标题</h1>\n'
    assert '>>>' not in result.stdout


def test_empty_input_and_duplicate_guard():
    """空stdin正常结束，重复stdin标识在消费前被拒绝。@return None。"""
    result=subprocess.run([sys.executable,'-m','mistletoe','-'],input='',text=True,capture_output=True,timeout=3)
    assert result.returncode==0 and result.stdout==''
    with unittest.TestCase().assertRaises(ValueError):
        cli.convert(['-','-'],HtmlRenderer)

