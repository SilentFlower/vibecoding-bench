"""CLI选项或写入失败不能提前截断输入/输出文件。"""
import contextlib
import io
import stat
import tempfile
from pathlib import Path
from unittest.mock import patch
from sqlparse.cli import main


def test_bad_options_preserve_inplace_and_existing_outfile():
    """无效indent_width保留所有既有字节。@return None。"""
    with tempfile.TemporaryDirectory() as temporary:
        source=Path(temporary)/'input.sql';target=Path(temporary)/'out.sql'
        source.write_bytes(b'select 1;');target.write_bytes(b'prior output')
        with contextlib.redirect_stderr(io.StringIO()):
            assert main([str(source),'--in-place','--indent_width','0'])==1
            assert main([str(source),'-o',str(target),'--indent_width','0'])==1
        assert source.read_bytes()==b'select 1;' and target.read_bytes()==b'prior output'


def test_success_mode_and_replace_failure_cleanup():
    """真实成功保持权限，替换失败不留下半文或临时文件。@return None。"""
    with tempfile.TemporaryDirectory() as temporary:
        path=Path(temporary)/'input.sql';path.write_text('select 1;');path.chmod(0o640)
        assert main([str(path),'--in-place','-k','upper'])==0 and path.read_text()=='SELECT 1;'
        assert stat.S_IMODE(path.stat().st_mode)==0o640
        before=path.read_bytes()
        with patch('sqlparse.cli.os.replace',side_effect=OSError('replace failed')),contextlib.redirect_stderr(io.StringIO()):
            assert main([str(path),'--in-place','-k','lower'])==1
        assert path.read_bytes()==before and len(list(path.parent.iterdir()))==1

