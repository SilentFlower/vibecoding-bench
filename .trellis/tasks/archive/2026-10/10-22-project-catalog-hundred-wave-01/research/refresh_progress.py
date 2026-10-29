"""按正式内容、实际准入报告和本地模拟证据刷新阶段内快照。"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path.cwd()
sys.path.insert(0, str(ROOT / 'orchestrator'))
from project_library import ProjectLibrary


WORKSPACE = ROOT / '.deploy/project-catalog-hundred/stage-01'
RESEARCH = Path(__file__).resolve().parent


def totals(library: ProjectLibrary) -> dict:
    """从实际manifest重算数量。@param library 内容库。@return 唯一项目、场景和任务数量。"""
    return {'projects': len(library.projects),
        'scenarios': sum(len(project.manifest['scenarios']) for project in library.projects.values()),
        'tasks': sum(len(scene['tasks']) for project in library.projects.values() for scene in project.manifest['scenarios'])}


def main() -> None:
    """只写非权威进度快照，不修改runner、固定规划或历史研究。@return None。"""
    formal, drafts = ProjectLibrary(ROOT / 'project_library'), ProjectLibrary(WORKSPACE / 'drafts')
    stage = json.loads((RESEARCH / 'source-index.json').read_text())
    planned = [row['slug'] for row in stage['projects']]
    # 正式目录写入可能早于交付收据，只有实际准入记录完成的项目才计阶段完成。
    completed = []
    for key in sorted(set(planned) & formal.projects.keys()):
        admission = RESEARCH / (key + '-admission.json')
        actual = json.loads(admission.read_text()) if admission.is_file() else {}
        if actual.get('stage') == 'formal_registered_local_verified' and actual.get('mock_status') == 'passed':
            completed.append(key)
    result = {'purpose': '阶段内进度快照，auto-loop权威状态仍由runner维护',
        'updated_at': datetime.now(timezone.utc).isoformat(), 'run_id': 'auto-20261021191233',
        'outstanding_action': 'run_implement', 'stage_required_projects': len(planned),
        'completed_current_stage_projects': len(completed), 'completed_project_keys': completed,
        'remaining_current_stage_projects': len(planned) - len(completed),
        'remaining_without_draft_projects': len(set(planned) - drafts.projects.keys()),
        'formal_totals': {**totals(formal), 'digest': formal.digest, 'version': formal.version},
        'draft_totals': totals(drafts), 'draft_projects': [], 'product_mock_batches': [],
        'next_internal_batch': [key for key in planned if key not in drafts.projects][:4],
        'real_model_calls': 0, 'production_touched': False, 'push_performed': False}
    for key, project in drafts.projects.items():
        admission = RESEARCH / (key + '-admission.json')
        actual = json.loads(admission.read_text()) if admission.is_file() else {}
        native = actual.get('all_expectations_met')
        if native is None:
            evidence = actual.get('native_evidence', [])
            native = bool(evidence) and all(row['actual_status'] == row['expected'] for row in evidence)
        result['draft_projects'].append({'project': key, 'scenarios': len(project.manifest['scenarios']),
            'tasks': sum(len(scene['tasks']) for scene in project.manifest['scenarios']),
            'native_draft_verified': native is True,
            'admission_report': str(admission.relative_to(ROOT)) if admission.is_file() else None,
            'admission_sha256': hashlib.sha256(admission.read_bytes()).hexdigest() if admission.is_file() else None,
            'admission_stage': actual.get('stage', 'draft_defined_pending_native'),
            'formal_registered': key in formal.projects})
    for bundle in sorted(WORKSPACE.glob('mock-batch-*')):
        if not bundle.is_dir():
            continue
        run = bundle / 'run-001'
        row = {'bundle': str(bundle.relative_to(ROOT)), 'evidence': str(run.relative_to(ROOT)),
            'status': 'running', 'browser_watch_started': True}
        archive = run / 'evidence/result.json'
        if archive.is_file():
            actual = json.loads(archive.read_text())
            row.update(status=actual['status'], browser_status=actual.get('browser_status'))
            cleanup = run / 'cleanup.json'
            row['cleanup_status'] = json.loads(cleanup.read_text())['status'] if cleanup.is_file() else 'pending'
        elif (run / 'runtime.json').is_file():
            progress = Path(json.loads((run / 'runtime.json').read_text())['root']) / 'progress.json'
            if progress.is_file():
                row['progress'] = json.loads(progress.read_text())
        result['product_mock_batches'].append(row)
    (RESEARCH / 'execution-progress.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'formal': result['formal_totals'], 'drafts': result['draft_totals'],
        'stage_completed': len(completed), 'stage_required': len(planned)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
