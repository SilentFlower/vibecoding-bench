"""只用本地合成配置核Dynaconf分层、输入归属及验证生命周期。"""
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

import dynaconf
from dynaconf import Dynaconf, ValidationError, Validator


def local(**values):
    """创建不读真实文件的独立配置。@param values 合成值。@return 惰性配置。"""
    return Dynaconf(settings_files=[], envvar_prefix='BUSINESS_SYNTHETIC', load_dotenv=False, **values)


def main() -> None:
    """核冻结业务事实，不访问Redis、Vault或其他外部后端。@return None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(dynaconf.__file__).resolve() == root / 'library/dynaconf/__init__.py'}
    task = sys.argv[1]
    with patch.dict(os.environ, {}, clear=True), tempfile.TemporaryDirectory(prefix='business-config-') as directory:
        base = Path(directory)
        if task == 'DC-U01':
            path = base / 'settings.toml'
            path.write_text('[default]\nname="Local"\nport=8000\n[production]\nport=9000\n')
            settings = Dynaconf(settings_files=[str(path)], environments=True, env='production',
                envvar_prefix='BUSINESS_SYNTHETIC', load_dotenv=False)
            before = (settings.NAME, settings.PORT)
            with settings.using_env('default'):
                inside = (settings.NAME, settings.PORT)
            after = (settings.NAME, settings.PORT)
            result['local_environment_layers_inherit_defaults_and_using_env_restores_context'] = (
                before == after == ('Local', 9000) and inside == ('Local', 8000)
                and settings.current_env.upper() == 'PRODUCTION')
        elif task == 'DC-U02':
            os.environ.update(BUSINESS_SYNTHETIC_PORT='9000', BUSINESS_SYNTHETIC_ENABLED='false',
                BUSINESS_SYNTHETIC_LABEL='"009"')
            settings = local(PORT=8000, ENABLED=True, LABEL='fallback')
            result['environment_values_are_parsed_with_explicit_string_quoting'] = (
                settings.PORT == 9000 and type(settings.PORT) is int
                and settings.ENABLED is False and settings.LABEL == '009' and type(settings.LABEL) is str)
        elif task == 'DC-C01':
            settings = local()
            settings.set('NESTED', {'items': [1, 2]}, validate=False)
            first = settings.NESTED['items']
            first.append(3)
            second = settings.NESTED['items']
            transient = list(first) == [1, 2, 3] and list(second) == [1, 2] and first is not second
            settings.set('NESTED.items', [1, 2, 3], validate=False)
            result['nested_list_reads_are_not_a_persistent_mutation_view'] = transient and list(settings.NESTED['items']) == [1, 2, 3]
        elif task == 'DC-C02':
            settings = local()
            data = {'EXISTING': 1}
            settings.update(data, OTHER=2, validate=False)
            original = {'EXISTING': 1}
            settings.update(dict(original), OTHER=3, validate=False)
            result['update_mutates_a_nonempty_supplied_mapping_when_combining_keywords'] = (
                data == {'EXISTING': 1, 'OTHER': 2} and original == {'EXISTING': 1}
                and settings.EXISTING == 1 and settings.OTHER == 3)
        elif task == 'DC-C03':
            settings = local(PORT=-1)
            settings.validators.register(Validator('PORT', gte=0), Validator('NAME', must_exist=True))
            returned = settings.validators.validate_all(raise_error=False)
            aggregated = None
            try:
                settings.validators.validate_all()
            except ValidationError as error:
                aggregated = error
            result['validate_all_already_returns_or_raises_the_complete_registered_error_set'] = (
                len(returned) == 2 and all(isinstance(error, ValidationError) for error in returned)
                and aggregated is not None and len(aggregated.details) == 2
                and 'PORT' in str(aggregated) and 'NAME' in str(aggregated))
        elif task == 'DC-P01':
            path = base / 'envs.toml'
            path.write_text('[dev]\nenabled=false\nport=1\n[prod]\nenabled=true\nport=-1\n')
            options = {'settings_files': [str(path)], 'environments': True,
                'envvar_prefix': 'BUSINESS_SYNTHETIC', 'load_dotenv': False}
            dev, prod = Dynaconf(env='dev', **options), Dynaconf(env='prod', **options)
            when = Validator('ENABLED', eq=True)
            shared = Validator('PORT', gte=0, when=when)
            initially_unbound = when.envs is None
            shared.validate(dev)
            shared_passed = True
            try:
                shared.validate(prod)
            except ValidationError:
                shared_passed = False
            fresh_rejected = False
            try:
                Validator('PORT', gte=0, when=Validator('ENABLED', eq=True)).validate(prod)
            except ValidationError:
                fresh_rejected = True
            result['conditional_validators_bind_environment_state_and_need_explicit_lifecycle_ownership'] = (
                initially_unbound and [env.upper() for env in when.envs] == ['DEV']
                and shared_passed and fresh_rejected and prod.PORT == -1 and prod.ENABLED is True)
        else:
            raise ValueError('未冻结的业务任务')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
