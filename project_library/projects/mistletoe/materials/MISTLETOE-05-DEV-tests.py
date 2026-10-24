"Public regression tests for MISTLETOE-05-DEV; the complete business contract is in materials/MISTLETOE-05-DEV-contract.md."
import os
import subprocess
import sys
import unittest
from mistletoe import cli, HtmlRenderer


def test_utf8_pipe_converts_once():
    "Verify utf8 pipe converts once."
    result=subprocess.run([sys.executable,'-m','mistletoe','-'],input='# 中文标题\n',text=True,capture_output=True,timeout=3)
    assert result.returncode==0 and result.stdout=='<h1>中文标题</h1>\n'
    assert '>>>' not in result.stdout


def test_empty_input_and_duplicate_guard():
    "Verify empty input and duplicate guard."
    result=subprocess.run([sys.executable,'-m','mistletoe','-'],input='',text=True,capture_output=True,timeout=3)
    assert result.returncode==0 and result.stdout==''
    with unittest.TestCase().assertRaises(ValueError):
        cli.convert(['-','-'],HtmlRenderer)

