"""实际执行上游完整Behave入口，场景与执行步骤分开记账。"""
from collections import Counter
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys

import docx


def main() -> None:
    """核固定原版BDD与候选来源，完整JSON另存而不把步骤充场景数。@return None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    project = root / 'library'
    output = Path('/evidence/behave.json')
    command = [sys.executable, '-m', 'behave', '--format', 'json', '--outfile', str(output), '--tags=-wip']
    completed = subprocess.run(command, cwd=project, capture_output=True, text=True, timeout=150)
    features = json.loads(output.read_text()) if output.is_file() else []
    nodes, steps, feature_statuses = [], Counter(), Counter()
    for feature in features:
        feature_statuses[feature['status']] += 1
        for element in feature.get('elements', []):
            if element['type'] != 'scenario':
                continue
            location = element['location'].replace(str(project) + '/', '')
            status = element['status']
            nodes.append({'id': location + '::' + element['name'], 'kind': 'BehaveScenario', 'outcome': status})
            for step in element['steps']:
                actual = step.get('result', {}).get('status', 'unexecuted')
                steps[actual] += 1
                if status == 'passed' and actual != 'passed':
                    raise ValueError('已通过场景含未通过或未执行步骤')
    counts = Counter(row['outcome'] for row in nodes)
    candidate = Path(docx.__file__).resolve() == project / 'src/docx/__init__.py'
    valid = (candidate and completed.returncode == 0 and nodes and counts['passed'] > 0
        and len({row['id'] for row in nodes}) == len(nodes) and set(counts) <= {'passed', 'skipped'}
        and set(feature_statuses) <= {'passed', 'skipped'})
    report = {'status': 'passed' if valid else 'failed', 'candidate_import': candidate, 'entry': command,
        'collected': len(nodes), 'passed': counts['passed'], 'skipped': counts['skipped'],
        'features': dict(feature_statuses), 'steps': dict(steps), 'nodes': nodes,
        'formatter_json_sha256': sha256(output.read_bytes()).hexdigest() if output.is_file() else None,
        'stdout': completed.stdout[-3000:], 'stderr': completed.stderr[-3000:], 'returncode': completed.returncode,
        'scope': '完整固定原版的额外官方BDD；执行步骤不计独立场景，不代替修改候选回归'}
    print(json.dumps(report))
    raise SystemExit(0 if valid else 1)


if __name__ == '__main__':
    main()
