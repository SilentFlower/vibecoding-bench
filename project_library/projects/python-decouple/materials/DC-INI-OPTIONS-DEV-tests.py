"""INI节与百分号插值必须可以显式选择。"""
from decouple import Config, RepositoryIni


def test_custom_section_literal_url(tmp_path):
    """自定义节的字面URL保留百分号。@param tmp_path 临时目录。@return None。"""
    path = tmp_path / 'settings.ini'
    path.write_text('[web]\nURL=https://x/a%20b\n', encoding='utf-8')
    config = Config(RepositoryIni(str(path), section='web', interpolation=False))
    assert config('URL') == 'https://x/a%20b'


def test_default_interpolation(tmp_path):
    """默认settings节及已有插值不变。@param tmp_path 临时目录。@return None。"""
    path = tmp_path / 'settings.ini'
    path.write_text('[settings]\nHOST=local\nURL=https://%(HOST)s/\n', encoding='utf-8')
    assert Config(RepositoryIni(str(path)))('URL') == 'https://local/'


def test_default_values_custom_section(tmp_path):
    """自定义节仍继承DEFAULT且实例互不影响。@param tmp_path 临时目录。@return None。"""
    path = tmp_path / 'settings.ini'
    path.write_text('[DEFAULT]\nPORT=7\n[web]\nNAME=one\n[settings]\nNAME=two\n', encoding='utf-8')
    assert RepositoryIni(str(path), section='web')['PORT'] == '7'
    assert RepositoryIni(str(path))['NAME'] == 'two'
