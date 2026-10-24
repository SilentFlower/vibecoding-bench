"""公开未占用输出路径回归。"""
from pathlib import Path
import pytest
import click
from click.testing import CliRunner
from click.newpath import NewPath

def test_existing_file_directory_and_dangling_link_are_rejected(tmp_path):
    file=tmp_path/'existing';file.write_text('keep');link=tmp_path/'link';link.symlink_to(tmp_path/'absent')
    for path in (file,tmp_path,link):
        with pytest.raises(click.BadParameter):
            NewPath().convert(str(path),None,None)
    assert file.read_text()=='keep'

def test_missing_path_preserves_requested_type_and_is_not_created(tmp_path):
    path=tmp_path/'new'
    assert NewPath(path_type=Path).convert(str(path),None,None)==path and not path.exists()

def test_real_command_does_not_run_for_occupied_output(tmp_path):
    calls=[]
    @click.command()
    @click.option('--output',type=NewPath())
    def command(output):
        calls.append(output)
    result=CliRunner().invoke(command,['--output',str(tmp_path)])
    assert result.exit_code==2 and calls==[]

def test_incompatible_flags_and_dash_are_rejected():
    with pytest.raises(TypeError):
        NewPath(exists=True)
    with pytest.raises(click.BadParameter):
        NewPath().convert('-',None,None)
