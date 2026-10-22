"""复用已提交的冻结配方工具，显式限定本阶段输出根。"""
from argparse import ArgumentParser
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
from json import dumps, loads
from pathlib import Path
from subprocess import check_output
import sys


def main() -> None:
    """校验已提交工具原件后运行指定模式，业务内容仍来自本阶段实际manifest。@return None。"""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['recipes', 'batch', 'progress'])
    parser.add_argument('--control-projects', nargs='+', default=[])
    options, arguments = parser.parse_known_args()
    root = Path.cwd()
    controls = options.control_projects
    if controls and options.mode != 'batch':
        raise ValueError('已有正式项目只允许作为批次验证控制')
    if options.mode in ('recipes', 'batch'):
        selector = ArgumentParser(add_help=False)
        selector.add_argument('--project')
        selector.add_argument('--projects', nargs='+')
        selector.add_argument('--batch')
        selected, remaining = selector.parse_known_args(arguments)
        keys = [selected.project] if options.mode == 'recipes' else selected.projects
        if not keys or any(not key or '/' in key or '..' in key for key in keys):
            raise ValueError('缺少明确合法的项目范围')
        for key in keys:
            path = Path(__file__).resolve().parent / (key + '-admission.json')
            if not path.is_file() or loads(path.read_text())['stage'] != 'native_verified_pending_mock':
                raise ValueError('必须先完成真实原生业务准入：' + key)
            if options.mode == 'batch':
                fixtures = Path.cwd() / '.deploy/project-catalog-hundred/stage-03/fixtures' / key
                if any(not (fixtures / name).is_file()
                        for name in ('recipes.json', 'recipe-overrides.json', 'review-protocol-proof.json')):
                    raise ValueError('配方冻结尚未完成，不创建模拟目录：' + key)
        if controls:
            from verify_delivery import files

            if (remaining or not selected.batch or len(set(controls)) != len(controls)
                    or set(controls) & set(keys)
                    or any(not key or '/' in key or '..' in key for key in controls)):
                raise ValueError('验证控制范围不明确或与新增项目重复')
            work = root / '.deploy/project-catalog-hundred/stage-03'
            catalog = loads((root / 'project_library/catalog.json').read_text())
            for key in controls:
                admission = loads((Path(__file__).parent / (key + '-admission.json')).read_text())
                formal = root / 'project_library/projects' / key
                draft = work / 'drafts/projects' / key
                manifest = loads((formal / 'project.json').read_text())
                environment = manifest['environment']
                if (key not in catalog['projects'] or admission['stage'] != 'formal_registered_local_verified'
                        or not admission['formal_registered'] or admission['mock_status'] != 'passed'
                        or files(formal) != files(draft)
                        or files(root / 'project_library/environments' / environment)
                            != files(work / 'drafts/environments' / environment)):
                    raise ValueError('控制项目并非当前正式内容的完整字节副本：' + key)
                if any(not (work / 'fixtures' / key / name).is_file()
                        for name in ('recipes.json', 'recipe-overrides.json', 'review-protocol-proof.json')):
                    raise ValueError('控制项目缺少原已验证配方：' + key)
            arguments = ['--batch', selected.batch, '--projects', *keys, *controls]
    name = {'recipes': 'freeze_mock_recipes.py', 'batch': 'freeze_mock_batch.py',
        'progress': 'refresh_progress.py'}[options.mode]
    source = root / '.trellis/tasks/10-22-project-catalog-hundred-wave-02/research' / name
    committed = check_output(['git', 'show', 'HEAD:' + str(source.relative_to(root))])
    if source.is_symlink() or source.read_bytes() != committed:
        raise ValueError('冻结工具必须与已提交原件逐字节相同')
    specification = spec_from_file_location('_committed_stage02_mock_recipe', source)
    if specification is None or specification.loader is None:
        raise ValueError('已提交配方模块无法加载')
    module = module_from_spec(specification)
    specification.loader.exec_module(module)
    # 这两个既有工具的输出仅由WORKSPACE控制，不改__file__或原脚本字节。
    module.WORKSPACE = root / '.deploy/project-catalog-hundred/stage-03'
    if options.mode == 'progress':
        module.RESEARCH = Path(__file__).resolve().parent
    sys.argv = [str(source), *arguments]
    print(dumps({'committed_tool': str(source.relative_to(root)), 'sha256': sha256(committed).hexdigest(),
        'workspace': str(module.WORKSPACE.relative_to(root))}), flush=True)
    module.main()
    if controls:
        identity_path = module.WORKSPACE / selected.batch / 'fixtures/catalog-identity.json'
        identity = loads(identity_path.read_text())
        identity.update(new_project_keys=keys, control_project_keys=controls)
        identity_path.write_text(dumps(identity, ensure_ascii=False, indent=2) + '\n')
        print(dumps({'new_projects': keys, 'existing_control_projects': controls,
            'control_replay_not_new_admission': True}, ensure_ascii=False))


if __name__ == '__main__':
    main()
