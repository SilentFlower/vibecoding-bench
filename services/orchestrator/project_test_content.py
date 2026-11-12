"""在测试专属临时目录构造调度夹具；不提供正式内容库生成入口。"""
import json
from pathlib import Path

from project_library import ProjectLibrary, snapshot_tree


REFERENCE_SOURCE = '''"""仅供隔离调度测试使用的确定性回调。"""


def evaluate(operator, request, fields):
    """返回夹具步骤结果。@param operator 步号。@param request 输入。@param fields 夹具标识。@return 确定性结果。"""
    return {"project": fields["project"], "step": int(operator), "items": request.get("items", [])}
'''

SEED_SOURCE = '''"""隔离调度测试夹具，不是真实工程项目。"""
import json
import sys

FIELDS = {fields!r}


def handle(request):
    """处理夹具基线。@param request 输入。@return 基线或未实现结果。"""
    if request.get("action", "overview") == "overview":
        return {{"project": FIELDS["project"], "step": 0, "items": request.get("items", [])}}
    return {{"error": "unsupported_action"}}


if __name__ == '__main__':
    for line in sys.stdin:
        if line.strip():
            print(json.dumps(handle(json.loads(line))))
'''


def create_project_fixture(root: Path) -> ProjectLibrary:
    """创建仅用于调度回归的百项目、二十步夹具。

    :param root: 调用方拥有、尚不存在的测试临时目录。
    :return: 加载后的测试内容库，不注册为正式项目来源。
    """
    root.mkdir(parents=True, exist_ok=False)
    (root/'reference_runtime.py').write_text(REFERENCE_SOURCE)
    keys = []
    for number in range(1, 101):
        key = f'project-{number:03d}'
        keys.append(key)
        destination = root/'projects'/key
        seed = destination/'seed'
        verification = destination/'verification'
        seed.mkdir(parents=True)
        verification.mkdir()
        fields = {'project': key}
        (seed/'app.py').write_text(SEED_SOURCE.format(fields=fields))
        (seed/'README.md').write_text('# 隔离调度测试夹具\n\n不得作为正式项目内容发布。\n')
        baseline = [{'input': {'action': 'overview', 'items': items},
            'expected': {'project': key, 'step': 0, 'items': items}} for items in ([], [{'value': number}])]
        steps, actions = [], {}
        for index in range(1, 21):
            action = f'fixture_step_{index:02d}'
            actions[action] = str(index)
            contract = {'action': action, 'fields': fields, 'options': {}}
            steps.append({'id': f'step-{index:02d}',
                'goal': 'Complete the isolated scheduling fixture step. Interface contract: '+json.dumps(contract),
                'milestone': f'phase-{(index-1)//5+1}',
                'requires': [] if index == 1 else [f'step-{index-1:02d}'],
                'checks': [{'input': {'action': action, 'items': items},
                    'expected': {'project': key, 'step': index, 'items': items}}
                    for items in ([], [{'value': number}], [{'value': index}, {'value': number}])]})
        manifest = {'schema': 1, 'project_key': key, 'title': f'Scheduling fixture {number:03d}',
            'category': 'test-fixture', 'source_topic_no': number,
            'description': 'Synthetic scheduling fixture; not a real engineering project.',
            'entrypoint': ['python3', 'app.py'], 'seed_digest': snapshot_tree(seed)['digest'],
            'baseline_checks': baseline, 'milestones': [{'id': f'phase-{index}',
                'title': f'Fixture phase {index}'} for index in range(1, 5)], 'steps': steps}
        (destination/'project.json').write_text(json.dumps(manifest)+'\n')
        (verification/'reference.json').write_text(json.dumps({'fields': fields, 'actions': actions})+'\n')
    (root/'catalog.json').write_text(json.dumps({'schema': 1, 'version': 'test-fixture-1', 'projects': keys})+'\n')
    return ProjectLibrary(root)
