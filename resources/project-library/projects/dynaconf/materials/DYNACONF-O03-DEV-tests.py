"Public regression tests for DYNACONF-O03-DEV; the complete business contract is in materials/DYNACONF-O03-DEV-contract.md."
from dynaconf import Dynaconf,Validator
from dynaconf.validator import ValidationError
from types import MappingProxyType
import pytest

def test_kwargs_override_settings_but_input_dictionary_is_untouched():
    "Verify kwargs override settings but input dictionary is untouched."
    settings=Dynaconf(environments=False);source={'VALUE':1};settings.update(source,VALUE=2,OTHER=3)
    assert settings.VALUE==2 and settings.OTHER==3 and source=={'VALUE':1}

def test_readonly_mapping_empty_mapping_and_generator_pairs_are_supported():
    "Verify readonly mapping empty mapping and generator pairs are supported."
    settings=Dynaconf(environments=False);settings.update(MappingProxyType({'A':1}),B=2)
    assert settings.A==1 and settings.B==2
    settings.update(iter([('C',3)]),D=4);assert settings.C==3 and settings.D==4
    empty={};settings.update(empty,E=5);assert empty=={}

def test_validation_failure_does_not_write_extra_keys_into_original_mapping():
    "Verify validation failure does not write extra keys into original mapping."
    settings=Dynaconf(environments=False,validators=[Validator('PORT',gt=0)],PORT=1);source={'PORT':-1}
    with pytest.raises(ValidationError):settings.update(source,EXTRA='new',validate=True)
    assert source=={'PORT':-1}
