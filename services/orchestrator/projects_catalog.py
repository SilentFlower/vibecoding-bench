"""新 Projects 的项目研究与工程目标目录，不包含对话或批次调度。"""
from __future__ import annotations

import re
from pathlib import Path

from project_library import ProjectLibrary, read_document, safe_relative


PROJECT_KEY = re.compile(r'^[a-z][a-z0-9-]{0,79}$')


class ProjectsCatalog:
    """将研究资料与已具备独立验收的工程目标分别提供给账号控制器。

    :param research: 原有逐仓研究目录。
    :param library: 已校验并冻结的内容资产，可为空。
    """

    def __init__(self, research: Path, library: ProjectLibrary | None) -> None:
        """保存只读资产入口，不创建工作目录。

        :param research: 项目研究目录。
        :param library: 冻结内容资产。
        :return: None。
        """
        self.research, self.library = research, library
        self._releases = {library.digest: self} if library else {}

    def for_work(self, work: dict):
        """按工作的冻结版本读取资产，软件更新不能将新合同套入原会话。

        :param work: 控制端保存的工作及内容版本。
        :return: 该工作的只读项目目录。
        """
        digest = work['library_digest']
        if digest in self._releases:
            return self._releases[digest]
        root = Path(work['library_root'])
        if (not self.library or root.is_symlink() or root.name != digest
                or root.resolve().parent != self.library.root.resolve().parent):
            raise ValueError('原工作冻结内容版本的目录归属不符')
        library = ProjectLibrary(root)
        if library.digest != digest:
            raise ValueError('原工作冻结内容损坏，保留现场并拒绝换用新合同')
        self._releases[digest] = ProjectsCatalog(self.research, library)
        return self._releases[digest]

    def proof_contract(self, work: dict, snapshots: dict) -> tuple[str, dict]:
        """为只读页面取得冻结合同元数据，不把页面结果作为执行授权。

        :param work: 数据库中的原通过工作，包含冻结目录、项目及目标归属。
        :param snapshots: 本次页面读取专用的合同快照，不能跨请求保留。
        :return: 原项目 seed 摘要及完整目标合同；归属或元数据异常时拒绝。
        """
        digest, key = work['library_digest'], work['project_key']
        if not self.library or not isinstance(key, str) or not PROJECT_KEY.fullmatch(key):
            raise ValueError('历史工程合同归属不符')
        cache_key = (work['library_root'], digest, key)
        if cache_key not in snapshots:
            try:
                if digest == self.library.digest:
                    manifest = self.library.projects[key].manifest
                else:
                    root = Path(work['library_root'])
                    if (root.is_symlink() or root.name != digest
                            or root.resolve().parent != self.library.root.resolve().parent):
                        raise ValueError('历史工程目录归属不符')
                    catalog = read_document(root / 'catalog.json')
                    if (not isinstance(catalog, dict) or type(catalog.get('schema')) is not int
                            or catalog['schema'] not in (2, 3) or not isinstance(catalog.get('projects'), list)
                            or key not in catalog['projects']):
                        raise ValueError('历史工程目录元数据不符')
                    name = catalog.get('project_manifest', 'project.json')
                    if name not in ('project.json', 'development.json') or catalog['schema'] != 3 and name != 'project.json':
                        raise ValueError('历史工程合同入口不符')
                    project = root / 'projects' / key
                    if (project.is_symlink() or (root / 'projects').is_symlink()
                            or not project.resolve().is_relative_to(root.resolve())):
                        raise ValueError('历史工程项目目录归属不符')
                    manifest = read_document(project / name)
                    if not isinstance(manifest, dict) or manifest.get('schema') != catalog['schema']:
                        raise ValueError('历史工程合同版本不符')
                if not isinstance(manifest, dict) or not isinstance(manifest.get('scenarios'), list):
                    raise ValueError('历史工程场景元数据不符')
                tasks = {}
                for scenario in manifest['scenarios']:
                    if not isinstance(scenario, dict) or not isinstance(scenario.get('tasks'), list):
                        raise ValueError('历史工程目标元数据不符')
                    for task in scenario['tasks']:
                        if not isinstance(task, dict):
                            raise ValueError('历史工程目标元数据不符')
                        if task.get('development_cycle') in ('feature', 'bug'):
                            if (task['id'] in tasks or not isinstance(task.get('evaluation'), dict)
                                    or not task['evaluation'].get('native')):
                                raise ValueError('历史工程目标合同不符')
                            tasks[task['id']] = task
                seed = manifest['seed_digest']
                if not isinstance(seed, str) or not seed:
                    raise ValueError('历史工程缺少源码摘要')
                # 页面核对已保存合同即可；全库源码及离线制品仍由真实执行的 for_work 校验。
                snapshots[cache_key] = (seed, tasks)
            except (ValueError, OSError, KeyError, TypeError):
                snapshots[cache_key] = None
                raise
        snapshot = snapshots[cache_key]
        if snapshot is None or work['objective_id'] not in snapshot[1]:
            raise ValueError('历史工程合同暂不可读取')
        return snapshot[0], snapshot[1][work['objective_id']]

    def listing(self) -> dict:
        """列出保留的研究项目，明确区分研究和可执行目标。

        :return: 项目列表与内容版本。
        """
        keys = {path.name.removesuffix('-roadmap-20.md') for path in self.research.glob('*-roadmap-20.md')}
        if self.library:
            keys.update(self.library.projects)
        return {'version': self.library.version if self.library else None,
            'projects': [self.project(key, detail=False) for key in sorted(keys) if PROJECT_KEY.fullmatch(key)]}

    def project(self, key: str, *, detail: bool = True) -> dict:
        """读取公开研究和业务目标，不向控制模型披露私有验收材料。

        :param key: 稳定项目标识。
        :param detail: 是否附带研究正文及公开业务材料。
        :return: 公开项目视图；不存在时抛出 ValueError。
        """
        if not isinstance(key, str) or not PROJECT_KEY.fullmatch(key):
            raise ValueError('项目标识不合法')
        project = self.library.projects.get(key) if self.library else None
        report = self.research / (key + '.md')
        roadmap = self.research / (key + '-roadmap-20.md')
        if project is None and not report.is_file() and not roadmap.is_file():
            raise ValueError('项目不存在')
        manifest = project.manifest if project else {}
        objectives = []
        for scenario in manifest.get('scenarios', []):
            for task in scenario['tasks']:
                if task.get('development_cycle') not in ('feature', 'bug'):
                    continue
                objectives.append({field: task[field] for field in ('id', 'goal', 'development_cycle')})
                objectives[-1]['requires'] = [{field: dependency[field] for field in ('task_id', 'artifact')}
                    for dependency in task['requires']]
                if detail:
                    objectives[-1].update(prompt=task['prompt'], allowed_paths=task['allowed_paths'],
                        materials={relative: self._text(project.root / safe_relative(relative))
                            for relative in dict.fromkeys([*task['materials'], *task.get('owner_materials', [])])})
        result = {'project_key': key, 'title': manifest.get('title', key),
            'description': manifest.get('description', ''), 'source': manifest.get('source'),
            'ready': bool(objectives), 'objectives': objectives,
            'research_available': report.is_file() or roadmap.is_file()}
        if detail:
            result['research'] = {'report': self._text(report), 'roadmap': self._text(roadmap)}
        return result

    def objective(self, key: str, objective_id: str) -> tuple[object, dict]:
        """取得控制端工程合同，供工作区准备及独立验收使用。

        :param key: 项目标识。
        :param objective_id: 工程目标标识。
        :return: 已冻结的项目定义和目标；未知或无程序验收时拒绝。
        """
        self.project(key, detail=False)
        if not self.library or key not in self.library.projects:
            raise ValueError('该项目目前仅有研究，尚未具备独立工程验收合同')
        project = self.library.projects[key]
        for scenario in project.manifest.get('scenarios', []):
            for task in scenario['tasks']:
                if task['id'] == objective_id and task.get('development_cycle') in ('feature', 'bug'):
                    if not task['evaluation'].get('native'):
                        raise ValueError('工程目标缺少独立程序验收')
                    return project, task
        raise ValueError('工程目标不存在')

    @staticmethod
    def _text(path: Path) -> str:
        if not path.exists():
            return ''
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 192 * 1024:
            raise ValueError('公开研究材料类型或大小不合法')
        return path.read_text(encoding='utf-8')
