"""公开回归：只识别UTF-8文件最开头的BOM，不损坏真实配置内容。"""
from pathlib import Path
from tempfile import TemporaryDirectory
from decouple import Config, RepositoryEnv, RepositoryIni


def test_env_initial_bom_and_unicode():
    """BOM不能成为首键的一部分。@return None。"""
    with TemporaryDirectory() as root:
        path = Path(root) / 'settings.env'
        path.write_bytes(b'\xef\xbb\xbf' + 'BOM_APP_NAME=咖啡\n'.encode())
        assert Config(RepositoryEnv(str(path)))('BOM_APP_NAME') == '咖啡'


def test_ini_initial_bom():
    """同样的兼容政策适用于INI首节。@return None。"""
    with TemporaryDirectory() as root:
        path = Path(root) / 'settings.ini'
        path.write_bytes(b'\xef\xbb\xbf[settings]\nBOM_APP_PORT=8443\n')
        assert Config(RepositoryIni(str(path)))('BOM_APP_PORT', cast=int) == 8443


def test_value_bom_is_preserved():
    """值内部BOM是业务数据，不能全局清除。@return None。"""
    with TemporaryDirectory() as root:
        path = Path(root) / 'settings.env'
        path.write_text('BOM_APP_VALUE=left\ufeffright\n', encoding='utf-8')
        assert Config(RepositoryEnv(str(path)))('BOM_APP_VALUE') == 'left\ufeffright'


def test_explicit_latin1_remains_available():
    """显式非UTF8编码及已有强制转换继续工作。@return None。"""
    with TemporaryDirectory() as root:
        path = Path(root) / 'settings.env'
        path.write_bytes('BOM_APP_VALUE=café\n'.encode('latin-1'))
        assert Config(RepositoryEnv(str(path), encoding='latin-1'))('BOM_APP_VALUE') == 'café'
