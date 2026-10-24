"Public regression tests for DC-INI-OPTIONS-DEV; the complete business contract is in materials/DC-INI-OPTIONS-DEV-contract.md."
from decouple import Config, RepositoryIni


def test_custom_section_literal_url(tmp_path):
    "Verify custom section literal url."
    path = tmp_path / 'settings.ini'
    path.write_text('[web]\nURL=https://x/a%20b\n', encoding='utf-8')
    config = Config(RepositoryIni(str(path), section='web', interpolation=False))
    assert config('URL') == 'https://x/a%20b'


def test_default_interpolation(tmp_path):
    "Verify default interpolation."
    path = tmp_path / 'settings.ini'
    path.write_text('[settings]\nHOST=local\nURL=https://%(HOST)s/\n', encoding='utf-8')
    assert Config(RepositoryIni(str(path)))('URL') == 'https://local/'


def test_default_values_custom_section(tmp_path):
    "Verify default values custom section."
    path = tmp_path / 'settings.ini'
    path.write_text('[DEFAULT]\nPORT=7\n[web]\nNAME=one\n[settings]\nNAME=two\n', encoding='utf-8')
    assert RepositoryIni(str(path), section='web')['PORT'] == '7'
    assert RepositoryIni(str(path))['NAME'] == 'two'
