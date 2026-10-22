"""仅按已归档的模拟、审计和完整交付收据完成逐仓本地准入记录。"""
from __future__ import annotations

from argparse import ArgumentParser
import hashlib
import json
from pathlib import Path
from shutil import copyfile
import sys


ROOT = Path.cwd()
RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'orchestrator'))
from project_library import ProjectLibrary


def read(path: Path) -> dict:
    """读取实际收据。@param path 普通文件。@return JSON内容。"""
    if path.is_symlink():
        raise ValueError('收据不能是链接')
    return json.loads(path.read_text())


def evidence(path: Path) -> dict:
    """记录实际文件摘要。@param path 已存在文件。@return 路径与SHA。"""
    return {'path': str(path.relative_to(ROOT)), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def main() -> None:
    """核正式目录、完整交付和每批真实成功后更新非权威研究记录。@return None。"""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--bundles', nargs='+', required=True, type=Path)
    parser.add_argument('--delivery', required=True, type=Path)
    parser.add_argument('--receipt', required=True, type=Path)
    options = parser.parse_args()
    library = ProjectLibrary(ROOT / 'project_library')
    delivery = read(options.delivery)
    assert delivery['status'] == 'passed' and delivery['catalog_digest'] == library.digest
    assert delivery['git_export']['status'] == delivery['docker_export']['status'] == 'passed'
    assert delivery['user_index_unchanged'] and not delivery['cleanup_errors']
    receipt = options.receipt.resolve()
    assert receipt.is_relative_to(RESEARCH) and not receipt.exists()
    copyfile(options.delivery, receipt)
    totals = (len(library.projects), sum(len(p.manifest['scenarios']) for p in library.projects.values()),
        sum(len(s['tasks']) for p in library.projects.values() for s in p.manifest['scenarios']))
    updated = []
    for bundle in options.bundles:
        bundle = bundle.resolve(strict=True)
        run = bundle / 'run-001'
        result_path, cleanup_path = run / 'evidence/result.json', run / 'cleanup.json'
        result, cleanup = read(result_path), read(cleanup_path)
        audit_path = RESEARCH / (bundle.name + '-audit.json')
        audit = read(audit_path)
        assert result['status'] == result['browser_status'] == cleanup['status'] == audit['status'] == 'passed'
        assert result['db_cross_checked'] is True
        browsers = [path for path in sorted((bundle / 'browser').glob('*/diagnostics/result.json'))
            if read(path)['status'] == 'passed']
        assert browsers, '缺少实际页面成功记录'
        identity = read(bundle / 'fixtures/catalog-identity.json')
        for key in identity['project_keys']:
            mapping = next(row for row in delivery['mock_mapping'] if row['project'] == key)
            assert mapping['project_and_environment_bytes_equal'] and mapping['mock_catalog_digest'] == identity['digest']
            path = RESEARCH / (key + '-admission.json')
            admission = read(path)
            assert key in library.projects and not admission.get('mock_status') == 'passed'
            admission.update(stage='formal_registered_local_verified', formal_registered=True, pending=[], mock_status='passed',
                formal_version=library.version, formal_digest=library.digest, full_delivery_files=delivery['files'],
                mock_evidence=[evidence(p) for p in (result_path, cleanup_path, audit_path, browsers[-1], receipt)])
            path.write_text(json.dumps(admission, ensure_ascii=False, indent=2) + '\n')
            note = RESEARCH / (key + '-admission.md')
            text = note.read_text().replace('当前仍是草稿：', '原生验证完成时仍是草稿：')
            text = text.replace('当前尚待产品链、页面／API／数据库及Git／Docker准入，不作正式注册或真实模型效果声明。',
                '原生阶段曾等待产品链、页面／API／数据库及Git／Docker准入；实际本地正式结果见下文。')
            text += ('\n## 本地正式准入\n\n' + bundle.name
                + '的真实调度、候选／独立评审、原生及默认／必要入口通过，页面／API／SQLite、材料、预算和用量审计通过，临时资源已清理。'
                + f'正式{library.version}累计{totals[0]}项目／{totals[1]}场景／{totals[2]}任务，完整{delivery["files"]}文件Git／Docker字节及执行位一致。'
                + f'实际逐项证据与SHA见同名JSON和{receipt.name}。真实模型调用0；尚未提交、推送或部署。\n')
            note.write_text(text)
            updated.append(key)
    print(json.dumps({'formal_version': library.version, 'updated_projects': updated,
        'delivery_files': delivery['files']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
