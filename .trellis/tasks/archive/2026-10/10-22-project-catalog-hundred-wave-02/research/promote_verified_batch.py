"""仅将已完成真实模拟和独立审计的小批追加到正式目录。"""
from argparse import ArgumentParser
from hashlib import sha256
import json
from pathlib import Path
from shutil import copytree, rmtree
import sys


ROOT = Path.cwd()
RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'orchestrator'))
from project_library import ProjectLibrary
from project_scenario_content import validate_environment, validate_scenario_project
from verify_delivery import files


def read(path: Path) -> dict:
    """读取现存的普通证明。@param path 目标。@return JSON。"""
    if path.is_symlink():
        raise ValueError('证明不能沿链接读取')
    return json.loads(path.read_text())


def main() -> None:
    """核独立成功与精确内容，再追加可回退的目录版本。@return None。"""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--bundles', nargs='+', type=Path, required=True)
    options = parser.parse_args()
    formal = ROOT / 'project_library'
    catalog = formal / 'catalog.json'
    previous = catalog.read_bytes()
    document = read(catalog)
    current = ProjectLibrary(formal)
    selected = []
    for bundle in options.bundles:
        bundle = bundle.resolve(strict=True)
        run = bundle / 'run-001'
        result, cleanup = read(run / 'evidence/result.json'), read(run / 'cleanup.json')
        audit = read(RESEARCH / (bundle.name + '-audit.json'))
        if (result['status'] != 'passed' or result.get('browser_status') != 'passed'
                or not result.get('db_cross_checked') or cleanup['status'] != 'passed' or audit['status'] != 'passed'):
            raise ValueError('真实模拟／浏览器／独立审计／清理未全部成功')
        subset = ProjectLibrary(bundle / 'library')
        if subset.digest != read(bundle / 'fixtures/catalog-identity.json')['digest']:
            raise ValueError('模拟内容身份已经变化')
        for key, project in subset.projects.items():
            if key in current.projects or any(row[0] == key for row in selected):
                raise ValueError('正式项目不能覆盖或重复注册')
            admission = read(RESEARCH / (key + '-admission.json'))
            if (admission['stage'] != 'native_verified_pending_mock'
                    or admission['source_commit'] != project.manifest['source']['commit']):
                raise ValueError('当前项目缺少独立原生准入')
            for row in admission['native_evidence']:
                evidence = ROOT / row['evidence']
                actual = read(evidence)
                if (sha256(evidence.read_bytes()).hexdigest() != row['sha256'] or not actual['expectation_met']
                        or actual['result']['status'] != row['expected']):
                    raise ValueError('原生原件摘要或期望不符')
            environment = project.manifest['environment']
            for path in (formal / 'projects' / key, formal / 'environments' / environment):
                if path.exists():
                    raise ValueError('正式未注册目标路径已存在，不能猜测归属')
            selected.append((key, project, bundle / 'library/environments' / environment))
    created = []
    try:
        for key, project, environment in selected:
            destination = formal / 'projects' / key
            copytree(project.root, destination)
            created.append(destination)
            target = formal / 'environments' / project.manifest['environment']
            copytree(environment, target)
            created.append(target)
            if files(project.root) != files(destination) or files(environment) != files(target):
                raise ValueError('正式复制字节或执行位不同')
            validate_scenario_project(destination, project.manifest, key)
            validate_environment(formal / 'environments', project.manifest['environment'])
            document['projects'].append(key)
        version = int(current.version.removeprefix('real-project-scenarios-v').removesuffix('-en')) + 1
        document['version'] = 'real-project-scenarios-v' + str(version) + '-en'
        catalog.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n')
        library = ProjectLibrary(formal)
        baseline = read(RESEARCH / 'formal-baseline.json')['files']
        actual = files(formal)
        if not all(actual.get(name) == value for name, value in baseline.items() if name != 'catalog.json'):
            raise ValueError('之前正式内容发生变化')
    except Exception:
        catalog.write_bytes(previous)
        for path in reversed(created):
            rmtree(path)
        raise
    print(json.dumps({'version': library.version, 'projects': len(library.projects),
        'scenarios': sum(len(project.manifest['scenarios']) for project in library.projects.values()),
        'tasks': sum(len(scene['tasks']) for project in library.projects.values() for scene in project.manifest['scenarios']),
        'digest': library.digest, 'added': [row[0] for row in selected],
        'delivery_still_required': True}, ensure_ascii=False))


if __name__ == '__main__':
    main()
