"""项目内容版本、受限文件快照与冻结的业务验收契约。"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from stat import S_ISLNK, S_ISREG


PROJECT_KEY = re.compile(r"^[a-z][a-z0-9-]{0,79}$")
MAX_TREE_BYTES = 128 * 1024 * 1024
MAX_TREE_FILES = 10000
MAX_JSON_BYTES = 4 * 1024 * 1024
IGNORED_DIRECTORIES = {".git", "__pycache__", ".pytest_cache"}


def canonical_json(value: object) -> bytes:
    """生成稳定 JSON 字节，用于版本与结果摘要。

    :param value: 可 JSON 编码的值。
    :return: 不依赖字典插入顺序的 UTF-8 字节。
    """
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False).encode("utf-8")


def digest_json(value: object) -> str:
    """计算规范 JSON 的内容摘要。

    :param value: 可编码对象。
    :return: SHA-256 十六进制摘要。
    """
    return hashlib.sha256(canonical_json(value)).hexdigest()


def safe_relative(value: object) -> str:
    """拒绝越界或含平台歧义的相对路径。

    :param value: 待校验路径。
    :return: 规范 POSIX 相对路径；非法时抛出 ValueError。
    """
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ValueError("项目相对路径不合法")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in value.split("/")):
        raise ValueError("项目路径不能越过内容根目录")
    return str(path)


def read_document(path: Path) -> object:
    """读取有大小和文件类型约束的 JSON。

    :param path: 根目录已由调用者限制的 JSON 路径。
    :return: 解码对象；不吞掉非法 JSON。
    """
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as source:
        metadata = os.fstat(source.fileno())
        if not S_ISREG(metadata.st_mode) or metadata.st_size > MAX_JSON_BYTES:
            raise ValueError("项目 JSON 类型或大小不合法")
        value = source.read(MAX_JSON_BYTES + 1)
    if len(value) > MAX_JSON_BYTES:
        raise ValueError("项目 JSON 超出大小上限")
    return json.loads(value)


def write_document(path: Path, value: object) -> None:
    """原子保存控制端私有 JSON。

    :param path: 仅控制端可写的目标路径。
    :param value: JSON 对象。
    :return: None。
    """
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=".project-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as target:
            target.write(canonical_json(value))
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def snapshot_tree(root: Path, objects: Path | None = None) -> dict:
    """在固定目录 fd 上读取源码和数据，拒绝链接、设备与无界产物。

    :param root: 需要封存的项目目录。
    :param objects: 可选的控制端内容对象目录。
    :return: 文件清单、总大小与稳定树摘要。
    """
    files, total = {}, 0
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for directory, folders, names, parent in os.fwalk(".", dir_fd=descriptor, follow_symlinks=False):
            for folder in list(folders):
                if folder in IGNORED_DIRECTORIES:
                    folders.remove(folder)
                elif S_ISLNK(os.stat(folder, dir_fd=parent, follow_symlinks=False).st_mode):
                    raise ValueError("项目目录不能是链接")
            for name in sorted(names):
                relative = safe_relative(str(PurePosixPath(directory) / name).removeprefix("./"))
                item = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
                with os.fdopen(item, "rb") as source:
                    metadata = os.fstat(source.fileno())
                    if not S_ISREG(metadata.st_mode):
                        raise ValueError(f"项目只允许普通文件：{relative}")
                    total += metadata.st_size
                    if total > MAX_TREE_BYTES or len(files) >= MAX_TREE_FILES:
                        raise ValueError("项目产物超出快照大小或文件数上限")
                    content = source.read(metadata.st_size + 1)
                    if len(content) != metadata.st_size:
                        raise ValueError("封存时文件发生变化")
                checksum = hashlib.sha256(content).hexdigest()
                files[relative] = {"digest": checksum, "size": len(content)}
                if objects is not None:
                    destination = objects / checksum[:2] / checksum
                    if destination.exists():
                        if destination.is_symlink() or hashlib.sha256(destination.read_bytes()).hexdigest() != checksum:
                            raise ValueError("内容对象摘要不一致")
                    else:
                        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                        temporary = destination.with_name(checksum + ".tmp-" + os.urandom(6).hex())
                        try:
                            temporary.write_bytes(content)
                            temporary.chmod(0o600)
                            os.replace(temporary, destination)
                        finally:
                            temporary.unlink(missing_ok=True)
    finally:
        os.close(descriptor)
    return {"schema": 1, "files": files, "bytes": total, "digest": digest_json(files)}


def materialize_snapshot(manifest: dict, objects: Path, destination: Path) -> None:
    """将控制端快照恢复到一个全新的目录。

    :param manifest: snapshot_tree 生成的清单。
    :param objects: 控制端内容对象根目录。
    :param destination: 尚不存在的目标目录。
    :return: None；不覆盖已有工作副本。
    """
    if manifest.get("schema") != 1 or digest_json(manifest.get("files")) != manifest.get("digest"):
        raise ValueError("项目快照摘要不合法")
    destination.mkdir(parents=True, exist_ok=False)
    destination.chmod(0o755)
    try:
        for relative, item in manifest["files"].items():
            path = destination / safe_relative(relative)
            checksum = item["digest"]
            if not re.fullmatch(r"[a-f0-9]{64}", checksum):
                raise ValueError("项目对象摘要不合法")
            source = objects / checksum[:2] / checksum
            content = source.read_bytes()
            if hashlib.sha256(content).hexdigest() != checksum or len(content) != item["size"]:
                raise ValueError("项目对象内容已损坏")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            path.chmod(0o644)
        for directory in destination.rglob('*'):
            if directory.is_dir():
                directory.chmod(0o755)
    except Exception:
        shutil.rmtree(destination)
        raise


@dataclass(frozen=True)
class ProjectDefinition:
    """保存一个已校验的项目定义。

    :param root: 冻结项目内容根目录。
    :param manifest: 冻结的业务、基线和路线对象。
    """

    root: Path
    manifest: dict

    def summary(self, *, include_steps: bool = False) -> dict:
        """返回不泄露参考实现和验收内部文件的页面摘要。

        :param include_steps: 是否附带步骤目标。
        :return: 可序列化的项目摘要。
        """
        result = {key: self.manifest[key] for key in
            ("project_key", "title", "category", "source_topic_no", "description", "seed_digest")}
        result["step_count"] = len(self.manifest["steps"])
        result["milestones"] = self.manifest["milestones"]
        if include_steps:
            result["steps"] = [{key: step[key] for key in ("id", "goal", "milestone", "requires")}
                for step in self.manifest["steps"]]
        return result


class ProjectLibrary:
    """校验和注册不可变项目内容版本。

    :param root: 源码或已注册的内容目录。
    :param minimum_projects: 生产内容数量下限，隔离测试可显式缩小。
    :param minimum_steps: 每项目步骤下限。
    """

    def __init__(self, root: Path, *, minimum_projects: int = 100, minimum_steps: int = 20) -> None:
        """加载并校验内容；参数契约见类说明。@return None。"""
        self.root = root
        catalog = read_document(root / "catalog.json")
        if not isinstance(catalog, dict) or type(catalog.get("schema")) is not int or catalog["schema"] != 1:
            raise ValueError("项目目录 schema 不合法")
        keys = catalog.get("projects")
        if (not isinstance(keys, list) or len(keys) < minimum_projects
                or any(not isinstance(key, str) or not PROJECT_KEY.fullmatch(key) for key in keys)
                or len(set(keys)) != len(keys)):
            raise ValueError("项目目录数量、标识或唯一性不合法")
        self.version = catalog.get("version")
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError("项目目录缺少内容版本")
        self.projects: dict[str, ProjectDefinition] = {}
        for key in keys:
            project_root = root / "projects" / key
            if project_root.is_symlink():
                raise ValueError("项目内容目录不能是链接")
            manifest = read_document(project_root / "project.json")
            self._validate(manifest, key, minimum_steps)
            actual = snapshot_tree(project_root / "seed")
            if actual["digest"] != manifest["seed_digest"]:
                raise ValueError(f"项目 {key} 初始版本摘要不一致")
            self.projects[key] = ProjectDefinition(project_root, manifest)
        self.digest = snapshot_tree(root)["digest"]

    @staticmethod
    def _validate(manifest: object, key: str, minimum_steps: int) -> None:
        if (not isinstance(manifest, dict) or type(manifest.get("schema")) is not int
                or manifest["schema"] != 1 or manifest.get("project_key") != key):
            raise ValueError(f"项目 {key} 定义归属不合法")
        for field in ("title", "category", "description", "seed_digest"):
            if not isinstance(manifest.get(field), str) or not manifest[field].strip():
                raise ValueError(f"项目 {key} 缺少 {field}")
        if type(manifest.get("source_topic_no")) is not int or manifest["source_topic_no"] <= 0:
            raise ValueError("项目来源题号不合法")
        if manifest.get("entrypoint") != ["python3", "app.py"]:
            raise ValueError("首版项目入口必须是受限的 python3 app.py")
        steps, milestones = manifest.get("steps"), manifest.get("milestones")
        if not isinstance(steps, list) or len(steps) < minimum_steps or not isinstance(milestones, list):
            raise ValueError(f"项目 {key} 路线长度不合法")
        milestone_ids = {item["id"] for item in milestones if isinstance(item, dict) and isinstance(item.get("id"), str)}
        if len(milestone_ids) != len(milestones) or not milestone_ids:
            raise ValueError("项目阶段定义不合法")
        previous = []
        for step in steps:
            if (not isinstance(step, dict) or not isinstance(step.get("id"), str)
                    or not PROJECT_KEY.fullmatch(step["id"]) or step["id"] in previous
                    or not isinstance(step.get("goal"), str) or not step["goal"].strip()
                    or step.get("milestone") not in milestone_ids
                    or step.get("requires") != previous[-1:]):
                raise ValueError(f"项目 {key} 步骤顺序或目标不合法")
            ProjectLibrary._validate_cases(step.get("checks"))
            previous.append(step["id"])
        ProjectLibrary._validate_cases(manifest.get("baseline_checks"))

    @staticmethod
    def _validate_cases(cases: object) -> None:
        if not isinstance(cases, list) or not cases or len(cases) > 32:
            raise ValueError("项目验收用例数量不合法")
        for case in cases:
            if (not isinstance(case, dict) or not isinstance(case.get("input"), dict)
                    or "expected" not in case or len(canonical_json(case)) > 65536):
                raise ValueError("项目验收输入或预期结果不合法")

    def install(self, data: Path) -> ProjectLibrary:
        """注册内容版本，存在相同摘要时只读复用。

        :param data: 调度器私有数据根。
        :return: 指向已冻结版本的新内容库对象。
        """
        releases = data / "project-library" / "releases"
        releases.mkdir(parents=True, exist_ok=True, mode=0o700)
        destination = releases / self.digest
        if not destination.exists():
            objects = data / "project-artifacts" / "objects"
            snapshot = snapshot_tree(self.root, objects)
            temporary = releases / (".register-" + os.urandom(8).hex())
            materialize_snapshot(snapshot, objects, temporary)
            try:
                os.rename(temporary, destination)
            except FileExistsError:
                shutil.rmtree(temporary)
        installed = ProjectLibrary(destination, minimum_projects=len(self.projects),
            minimum_steps=min(len(p.manifest["steps"]) for p in self.projects.values()))
        if installed.digest != self.digest:
            raise ValueError("已注册内容版本已损坏")
        return installed
