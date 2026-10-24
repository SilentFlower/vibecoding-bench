"Public regression tests for DYNACONF-O06-DEV; the complete business contract is in materials/DYNACONF-O06-DEV-contract.md."
from dynaconf import Dynaconf
from dynaconf.vendor.click.testing import CliRunner
import dynaconf.cli as cli
import json

def test_multiple_case_insensitive_patterns_select_union_without_duplicates(monkeypatch):
    "Verify multiple case insensitive patterns select union without duplicates."
    settings=Dynaconf(environments=False,DATABASE_URL='db',DATABASE_PORT=3,CACHE_SIZE=4,OTHER=5);monkeypatch.setattr(cli,'settings',settings,raising=False)
    result=CliRunner().invoke(cli._list,['--json','--match','database_*','--match','*SIZE','--match','*URL'])
    assert result.exit_code==0 and json.loads(result.output)=={'DATABASE_URL':'db','DATABASE_PORT':3,'CACHE_SIZE':4}

def test_empty_matches_exact_key_conflict_and_output_file_use_same_selection(tmp_path,monkeypatch):
    "Verify empty matches exact key conflict and output file use same selection."
    settings=Dynaconf(environments=False,ONE=1,TWO=2);monkeypatch.setattr(cli,'settings',settings,raising=False);runner=CliRunner()
    result=runner.invoke(cli._list,['--json','--match','missing*']);assert result.exit_code==0 and json.loads(result.output)=={}
    assert runner.invoke(cli._list,['--json','--match','*','--key','ONE']).exit_code!=0
    output=tmp_path/'selected.json';result=runner.invoke(cli._list,['--json','--match','ONE','--output',str(output)])
    assert result.exit_code==0 and json.loads(output.read_text())=={'ONE':1}

def test_literal_metacharacters_and_legacy_single_key_keep_original_data(monkeypatch):
    "Verify literal metacharacters and legacy single key keep original data."
    settings=Dynaconf(environments=False,ABC=1,ABD=2,OTHER=3);before=settings.as_dict();monkeypatch.setattr(cli,'settings',settings,raising=False)
    result=CliRunner().invoke(cli._list,['--json','--match','AB[CD]'])
    assert result.exit_code==0 and json.loads(result.output)=={'ABC':1,'ABD':2}
    legacy=CliRunner().invoke(cli._list,['--json','--key','OTHER']);assert json.loads(legacy.output)=={'OTHER':3}
    assert settings.as_dict()==before
