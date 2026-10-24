"""Public regressions: recognize only an initial BOM in a UTF-8 file without corrupting configuration data."""
from pathlib import Path
from tempfile import TemporaryDirectory
from decouple import Config, RepositoryEnv, RepositoryIni


def test_env_initial_bom_and_unicode():
    """Keep the BOM out of the first key. @return None."""
    with TemporaryDirectory() as root:
        path = Path(root) / 'settings.env'
        path.write_bytes(b'\xef\xbb\xbf' + 'BOM_APP_NAME=咖啡\n'.encode())
        assert Config(RepositoryEnv(str(path)))('BOM_APP_NAME') == '咖啡'


def test_ini_initial_bom():
    """Apply the same compatibility policy to the first INI section. @return None."""
    with TemporaryDirectory() as root:
        path = Path(root) / 'settings.ini'
        path.write_bytes(b'\xef\xbb\xbf[settings]\nBOM_APP_PORT=8443\n')
        assert Config(RepositoryIni(str(path)))('BOM_APP_PORT', cast=int) == 8443


def test_value_bom_is_preserved():
    """Preserve a BOM inside a value as business data instead of stripping it globally. @return None."""
    with TemporaryDirectory() as root:
        path = Path(root) / 'settings.env'
        path.write_text('BOM_APP_VALUE=left\ufeffright\n', encoding='utf-8')
        assert Config(RepositoryEnv(str(path)))('BOM_APP_VALUE') == 'left\ufeffright'


def test_explicit_latin1_remains_available():
    """Preserve explicit non-UTF-8 encodings and existing casts. @return None."""
    with TemporaryDirectory() as root:
        path = Path(root) / 'settings.env'
        path.write_bytes('BOM_APP_VALUE=café\n'.encode('latin-1'))
        assert Config(RepositoryEnv(str(path), encoding='latin-1'))('BOM_APP_VALUE') == 'café'
