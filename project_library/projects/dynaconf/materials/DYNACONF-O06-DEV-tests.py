"""CLI按多个明确glob筛选真实配置键，输出与原单键模式区分。"""
from dynaconf import Dynaconf
from dynaconf.vendor.click.testing import CliRunner
import dynaconf.cli as cli
import json

def test_multiple_case_insensitive_patterns_select_union_without_duplicates(monkeypatch):
    """真实list --json输出只含匹配配置，重复匹配不重复数据。@return None。"""
    settings=Dynaconf(environments=False,DATABASE_URL='db',DATABASE_PORT=3,CACHE_SIZE=4,OTHER=5);monkeypatch.setattr(cli,'settings',settings,raising=False)
    result=CliRunner().invoke(cli._list,['--json','--match','database_*','--match','*SIZE','--match','*URL'])
    assert result.exit_code==0 and json.loads(result.output)=={'DATABASE_URL':'db','DATABASE_PORT':3,'CACHE_SIZE':4}

def test_empty_matches_exact_key_conflict_and_output_file_use_same_selection(tmp_path,monkeypatch):
    """无匹配为合法空集合，--key冲突明确，文件输出不混入未选键。@return None。"""
    settings=Dynaconf(environments=False,ONE=1,TWO=2);monkeypatch.setattr(cli,'settings',settings,raising=False);runner=CliRunner()
    result=runner.invoke(cli._list,['--json','--match','missing*']);assert result.exit_code==0 and json.loads(result.output)=={}
    assert runner.invoke(cli._list,['--json','--match','*','--key','ONE']).exit_code!=0
    output=tmp_path/'selected.json';result=runner.invoke(cli._list,['--json','--match','ONE','--output',str(output)])
    assert result.exit_code==0 and json.loads(output.read_text())=={'ONE':1}

def test_literal_metacharacters_and_legacy_single_key_keep_original_data(monkeypatch):
    """glob不是正则执行，原key模式与settings存储保持。@return None。"""
    settings=Dynaconf(environments=False,ABC=1,ABD=2,OTHER=3);before=settings.as_dict();monkeypatch.setattr(cli,'settings',settings,raising=False)
    result=CliRunner().invoke(cli._list,['--json','--match','AB[CD]'])
    assert result.exit_code==0 and json.loads(result.output)=={'ABC':1,'ABD':2}
    legacy=CliRunner().invoke(cli._list,['--json','--key','OTHER']);assert json.loads(legacy.output)=={'OTHER':3}
    assert settings.as_dict()==before
