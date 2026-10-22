#!/usr/bin/env python3
"""v3 两镜像的联合构建、冲突检查及受限启停入口。"""
import argparse
import fcntl
import hashlib
import gzip
import shutil
import tempfile
import tarfile
import json
import os
import re
import shlex
import socket
import sqlite3
import subprocess
import sys
import uuid
import time
import urllib.error
import urllib.request
from pathlib import Path
from stat import S_ISREG, S_ISSOCK
from urllib.parse import quote

REPO = Path(__file__).resolve().parents[2]
COMPOSE = Path(__file__).with_name("compose.yml")
# 独立部署脚本复用镜像内的纯预算模块，避免预检和容器解释不同单位。
sys.path.insert(0, str(REPO / "orchestrator"))
from resource_budget import account_limits, isolated_account_limits


def command(*arguments: str, capture: bool = False, environment=None) -> str:
    """以 argv 执行命令，秘密不写入命令行或输出。

    :param arguments: 完整 argv
    :param capture: 是否捕获 stdout
    :param environment: 进程环境
    :return: 捕获内容或空字符串
    """
    result = subprocess.run(arguments, cwd=REPO, env=environment, check=True,
        stdout=subprocess.PIPE if capture else None, text=True)
    return result.stdout or ""


def load_environment(path: Path) -> dict:
    """读取受限 .env 格式，拒绝 shell 语法与重复键。

    :param path: 配置文件
    :return: 配置值；不执行配置内容
    """
    values = {}
    for line in path.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, separator, raw = line.partition("=")
        key = key.strip()
        if not separator or not re.fullmatch(r"V3_[A-Z0-9_]+", key) or key in values:
            raise ValueError("配置包含未知格式或重复键")
        parts = shlex.split(raw, comments=False)
        if len(parts) > 1:
            raise ValueError("配置值含空格时需要加引号")
        values[key] = parts[0] if parts else ""
    return values


def inspect_images(values: dict) -> dict:
    """检查两个角色镜像与联合版本清单完全一致。

    :param values: 部署配置
    :return: 版本清单
    """
    manifest = json.loads(Path(values["V3_RELEASE_MANIFEST"]).read_text())
    if manifest.get("schema") != 3:
        raise ValueError("版本清单格式不匹配")
    if manifest.get("layout_version") not in (1, 2):
        raise ValueError("版本清单隔离布局不受支持")
    if values.get("V3_RELEASE", manifest["release"]) != manifest["release"]:
        raise ValueError("配置批次与清单不一致")
    values["V3_RELEASE"] = manifest["release"]
    for role in ("control", "account"):
        name = values[f"V3_{role.upper()}_IMAGE"]
        if name.endswith(":latest") or ":v3-" not in name:
            raise ValueError("必须使用独立 v3 批次标签，禁止 latest")
        info = json.loads(command("docker", "image", "inspect", name, capture=True))[0]
        entry = manifest["images"][role]
        labels = info["Config"]["Labels"] or {}
        if entry["reference"] != name or not _local_image_matches(name, info, entry):
            raise ValueError("镜像 digest 与清单不匹配")
        if entry.get("platform") and entry["platform"] != info.get("Os", "") + "/" + info.get("Architecture", ""):
            raise ValueError("镜像平台与清单不匹配")
        if labels.get("vibebench.product") != "v3" or labels.get("vibebench.role") != role:
            raise ValueError("镜像产品或角色不匹配")
        if manifest["layout_version"] == 2 and labels.get("vibebench.isolation-version") != "2":
            raise ValueError("联合镜像缺少三角色隔离能力")
        for label, key in (("release", "release"), ("parent-revision", "parent_revision"), ("gateway-revision", "gateway_revision")):
            if labels.get("vibebench." + label) != manifest[key]:
                raise ValueError("镜像构建批次不匹配")
    return manifest


def preflight(values: dict) -> Path:
    """拒绝旧资源重叠、端口占用和不匹配版本。

    :param values: 部署配置
    :return: 独立数据根的规范路径
    """
    deployment = values["V3_DEPLOYMENT_ID"]
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,35}", deployment):
        raise ValueError("部署标识不合法")
    for key in ("V3_INTERNAL_TOKEN", "V3_SESSION_SECRET", "V3_ADMIN_PASSWORD"):
        if len(values.get(key, "")) < 32:
            raise ValueError(f"{key} 至少需要 32 字符")
    supplied = Path(values["V3_DATA_ROOT"])
    root = supplied.resolve()
    if not supplied.is_absolute() or root in (Path("/"), Path("/srv"), REPO) or "v3" not in root.name:
        raise ValueError("请使用独立且名称含 v3 的绝对数据目录")
    ids = command("docker", "ps", "-aq", capture=True).split()
    containers = json.loads(command("docker", "inspect", *ids, capture=True)) if ids else []
    port = int(values.get("V3_HOST_PORT", "18080"))
    address = values.get("V3_BIND_ADDRESS", "127.0.0.1")
    owned_port = False
    for container in containers:
        labels = container["Config"].get("Labels") or {}
        own = labels.get("vibebench.product") == "v3" and labels.get("vibebench.deployment") == deployment
        for mount in container.get("Mounts", []):
            source = Path(mount["Source"]).resolve()
            if not own and (source == root or source in root.parents or root in source.parents):
                raise ValueError("数据挂载与其它部署重叠")
        name = container["Name"].lstrip("/")
        account_prefix = "v3-" + hashlib.sha256(deployment.encode()).hexdigest()[:12] + "-account-"
        if (name.startswith(f"vibebench-v3-{deployment}-") or name.startswith(account_prefix)) and not own:
            raise ValueError("容器名称被其它部署占用")
        for container_port, bindings in (container.get("HostConfig", {}).get("PortBindings") or {}).items():
            for binding in bindings or []:
                if int(binding.get("HostPort") or 0) == port and binding.get("HostIp", "") in ("", "0.0.0.0", "::", address):
                    if (own and labels.get("vibebench.role") == "gateway" and container_port == "5674/tcp"
                            and binding.get("HostIp", "") == address):
                        owned_port = owned_port or bool(container.get("State", {}).get("Running"))
                        continue
                    raise ValueError("宿主端口已被容器发布，拒绝启动")
    network_name = f"vibebench-v3-{deployment}"
    networks = [json.loads(line) for line in command("docker", "network", "ls", "--format", "{{json .}}", capture=True).splitlines()]
    for network in networks:
        if network["Name"] == network_name:
            info = json.loads(command("docker", "network", "inspect", network_name, capture=True))[0]
            labels = info.get("Labels") or {}
            if labels.get("vibebench.product") != "v3" or labels.get("vibebench.deployment") != deployment:
                raise ValueError("网络名称被其它部署占用")
    # 自有网关允许重复 up；其它进程或 Docker NAT 占用仍在预检拒绝。
    if not owned_port:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind((address, port))
    inspect_images(values)
    marker = root / ".v3-deployment.json"
    if marker.exists():
        if json.loads(marker.read_text()).get("deployment") != deployment:
            raise ValueError("数据目录属于其它部署")
    elif root.exists() and any(root.iterdir()):
        raise ValueError("非空数据目录缺少 v3 归属标记，拒绝接管")
    memory = {line.split(":", 1)[0]: int(line.split()[1]) * 1024
        for line in Path("/proc/meminfo").read_text().splitlines()
        if line.startswith(("MemAvailable:", "SwapFree:"))}
    active_limit = int(values.get("V3_MAX_ACTIVE_ACCOUNTS", "1"))
    account_memory, total_memory = account_limits(values.get("V3_ACCOUNT_MEMORY", "4g"), values.get("V3_ACCOUNT_SWAP", "0"))
    isolated_account_limits(values.get("V3_ACCOUNT_MEMORY", "4g"), values.get("V3_ACCOUNT_SWAP", "0"))
    database = root / "bench/db.sqlite"
    if database.is_file():
        if not database.resolve().is_relative_to(root):
            raise ValueError("数据库路径不属于本部署")
        with sqlite3.connect("file:" + quote(str(database), safe="/") + "?mode=ro", uri=True) as connection:
            if connection.execute("SELECT 1 FROM sqlite_master WHERE name='account_environments'").fetchone():
                # 已有账号保留首次限额；下调全局配置不能让预检低估下一次唤醒的额度。
                for saved, in connection.execute("SELECT fingerprint_json FROM account_environments"):
                    fingerprint = json.loads(saved)
                    ram, combined = account_limits(fingerprint["mem"], fingerprint.get("swap", "0"))
                    isolated_account_limits(fingerprint["mem"], fingerprint.get("swap", "0"))
                    if ram > account_memory or combined - ram > total_memory - account_memory:
                        raise ValueError("已有账号固化预算超过当前配置，请提高部署预算后再启动")
    if active_limit < 1 or float(values.get("V3_ACCOUNT_CPUS", "2")) <= 0:
        raise ValueError("账号 CPU、内存或活跃环境预算无效")
    # 账号预算与运维余量分开；小内存部署无需绕过完整归属和镜像预检。
    headroom = int(values.get("V3_MEMORY_HEADROOM_BYTES", str(256 * 1024**2)))
    if headroom < 0:
        raise ValueError("内存余量不能为负数")
    minimum = max(int(values.get("V3_MIN_FREE_MEMORY_BYTES", "0")), active_limit * account_memory + headroom)
    if memory.get("MemAvailable", 0) < minimum:
        raise ValueError("宿主可用内存不足，拒绝启动")
    swap = total_memory - account_memory
    if swap:
        if memory.get("SwapFree", 0) < active_limit * swap:
            raise ValueError("宿主空闲 swap 不足，拒绝启动")
        if json.loads(command("docker", "info", "--format", "{{json .SwapLimit}}", capture=True)) is not True:
            raise ValueError("Docker 不支持 swap 限额，拒绝启动")
    return root


def _public_source_directory_digest(root: Path) -> str:
    """核对固定上游夹具目录的全部字节与执行位，拒绝额外文件及链接。

    :param root: 已审查的真实上游目录。
    :return: 有序完整文件清单摘要。
    """
    if root.is_symlink() or not root.is_dir():
        raise ValueError('固定上游夹具目录不能是链接或缺失')
    files = []
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('固定上游夹具目录包含链接')
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError('固定上游夹具目录包含特殊文件')
        files.append([str(path.relative_to(root)), hashlib.sha256(path.read_bytes()).hexdigest(),
            bool(path.stat().st_mode & 0o111)])
    return hashlib.sha256(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def source_snapshot_ignore(directory: str, names: list[str]) -> set[str]:
    """过滤构建快照，仅保留精确摘要校验的上游公开原件。

    :param directory: 当前源码目录。
    :param names: shutil 提供的直接子项名称。
    :return: 仍应排除的名称集合。
    """
    ignored = set(shutil.ignore_patterns('.git','target','node_modules','__pycache__','.env','.env.*','*.log')(directory,names))
    if not ignored:
        return ignored
    resolved_directory = Path(directory).resolve()
    public_files = {
        'project_library/projects/flask/seed/library/tests/test_apps/.env': '3739562018bb8d8aeddbb540fb4c53e61af5385fb4d3b613e784057c3129ccc0',
        'project_library/projects/dynaconf/seed/library/tests/.env': '5c3cc246f660d747b5e4941403b45417a22707abea4f3e5dadecf4725eb3fbc7',
        'project_library/projects/dynaconf/seed/library/tests_functional/issues/1000_django_attribute_error/flab/.env': 'e62ccfcf912f860db8cd4b8740c556d5c9bbad47a6dd6d4d3ee1262359f9f303',
        'project_library/projects/dynaconf/seed/library/tests_functional/issues/160_path_traversal_fixed/.env': 'a9b9a1244196b0fe2149c93bccad4f00a6ca8bf7d29f3a682c2a5a9068bf42d8',
        'project_library/projects/dynaconf/seed/library/tests_functional/issues/166_renamed_global_env/.env': '0229f7106eee0bd601c3fa39c3de1a41971b987bf23b0a383db4d5925d680306',
        'project_library/projects/dynaconf/seed/library/tests_functional/issues/169_renamed_settings_module/.env': 'e84d120432819718be12a0a10e2e0d3fd49545876cd10e873bc4a6f345c55bde',
        'project_library/projects/dynaconf/seed/library/tests_functional/issues/182_multiple_locations/.env': 'd4eb6ec91dd0d24ea2a7ef86c777b468b0793a2c5a16fbb83e877a76aac36e2a',
        'project_library/projects/dynaconf/seed/library/tests_functional/issues/184_ipython/.env': '9ffe566fe25f5f9e9b19f2ab91b087ebfe9fef1082941bbce1f8d11400d86387',
        'project_library/projects/dynaconf/seed/library/tests_functional/issues/251_dotted_unexistent/.env': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
        'project_library/projects/dynaconf/seed/library/tests_functional/issues/266_envvar_from_env_override/.env': '49005ce7e9f1f46c93b733a264d56cba7e4597fb4d903f01b73f3c9556adacc0',
        'project_library/projects/dynaconf/seed/library/tests_functional/issues/288_null_values/.env': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
        'project_library/projects/dynaconf/seed/library/tests_functional/issues/306_merge_replace/.env': '691936f8ca331c4f3d7009cbd014f95f8d209cf567b7f46f9889a809cd4f29df',
        'project_library/projects/dynaconf/seed/library/tests_functional/issues/325_flask_dot_env/.env': '9eeb72df365e38d96f31a5b19d3e0ee10f281f2f298804d47086e8a75ae97561',
        'project_library/projects/dynaconf/seed/library/tests_functional/issues/392_evaluate_nested_structures/.env': '1c3fb8ac784b1c8b6f39f4ff84c4c062c36150f773958e914fe63df5065a0d0c',
        'project_library/projects/dynaconf/seed/library/tests_functional/issues/445_casting/.env': 'f24ec21448bcda7101281e886add47b28ff17ecb029dc243187996c25c4db083',
        'project_library/projects/dynaconf/seed/library/tests_functional/issues/449_django_lazy_path/.env': '4932857a4ec6e345c34b530700b2202481adfac420f74796b7f5e15e199db7a4',
        'project_library/projects/dynaconf/seed/library/tests_functional/issues/709_yaml_merge_with_env/.env': '26a9bc4e3b771bd2d2958b302e57f214108ff9d9b8015bfd083a7e0b8dfbe425',
        'project_library/projects/dynaconf/seed/library/tests_functional/issues/720_load_dotenv/.env': '9fb182573df36d42a8b77ce7c515b48f3499e5c2feb609b6af8e625e832189ce',
        'project_library/projects/dynaconf/seed/library/tests_functional/issues/722_docs_example/.env': '957bb29c65b70164bb403b5bf811d51c08bb026d5b37bbd5c9da7fbdd17a2761',
        'project_library/projects/dynaconf/seed/library/tests_functional/issues/869_order_break_parsing/.env': '8f9040d468d689f9934a8a656ca785e914647e3a189e887c4359e45496a6d47a',
        'project_library/projects/dynaconf/seed/library/tests_functional/issues/905_item_duplication_in_list/.env': 'c89405332a78bf9e65bca90701f60cdd27053143d3bc9a2c3c97792b9890843a',
        'project_library/projects/dynaconf/seed/library/tests_functional/issues/976_True_False/.env': '473b8e8350d254cb005cc67be4cac06bda12956fb8e7ca828425263a3b08cecc',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/app/.env': '777264dd18df422f8f794521bfa9d4df6cdee25e92232c8f1ce636a342939152',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/app_with_dotenv/.env': 'dd3ac49c2cbfda9301488d9425e6edee7c2caf5245547c5929d75c22369ecf88',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/cli_override_argparse/.env': '0135c01d8fad3a5477cb375ae264a1e81626a3d12f1a1b6c13430d2a0f5f0c1b',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/click_override_generic/.env': '0135c01d8fad3a5477cb375ae264a1e81626a3d12f1a1b6c13430d2a0f5f0c1b',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/click_override_strict/.env': '0135c01d8fad3a5477cb375ae264a1e81626a3d12f1a1b6c13430d2a0f5f0c1b',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/common-encoding/.env': 'b4a0a86f86306fc14a142b417f45764d75132fff17beb8def426864d885ab517',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/common/.env': '2ca58783ea2282fe761a9ce7bd21a8897fee85b265186a065f734e09773aa826',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/configure/.env': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/custom_loader/.env': '604fec6743fb6b1db43136024026e0ca71df11fdc0e9f10046860cbc7f5995ba',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/django_example/.env': '47e710094502b1d017cde94894653b2b68b9d34f10c3dc456a7947284d2d7372',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/django_example_compat/config/.env': '1b853d29356f6dc86627b414f6945e1f4894b2d7309e4c28d6fdf99e834aa91e',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/django_pytest/.env': '5779d55a759783a5f8079440516e9825ae454dd1985d955ecf21711d4a7fa865',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/django_pytest_pure/.env': '5779d55a759783a5f8079440516e9825ae454dd1985d955ecf21711d4a7fa865',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/dotenv_loaded_if_enabled/.env': 'fa5cf748bd367b3dabe85045d1273bb0b1dcc9ceaf8c9f4bb60717adf586eb89',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/dotenv_not_loaded_by_default/.env': 'fa5cf748bd367b3dabe85045d1273bb0b1dcc9ceaf8c9f4bb60717adf586eb89',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/dunder/.env': '68de277b7faac289daddce616619cb8c5c4fdc7576303a5019294fcac09ca14c',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/dynaconf_merge/.env': 'a0ea99115067c7650fcbc8818be325163e36e3846a2374ef2839014d6d824ef5',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/envless_mode/.env': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/envs/.env': '0135c01d8fad3a5477cb375ae264a1e81626a3d12f1a1b6c13430d2a0f5f0c1b',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/envvar_prefix/.env': '18c5c779c2829542389819287f0c984c875358d9e839aba5ad360c9550dc8478',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/flask_with_commentjson/.env': '5f9b2db8725ff94f0044b2014207940e467dfd1e8cda03f9e795902d2c618cf0',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/flask_with_dotenv/.env': 'e30fe4b9213098276e35cc6feb3eb0272b320d790dd1183465289249f0fd7402',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/flask_with_ini/.env': 'dcf76abbc07bf6beb82a4a36dfb4ba5a03a96b0faedb4f4e0a95db6ba8ae807b',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/flask_with_json/.env': '5f9b2db8725ff94f0044b2014207940e467dfd1e8cda03f9e795902d2c618cf0',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/flask_with_toml/.env': '2d4bcf2d190e07c22851f6ea5abe1849d7fd07614ed7eb908e009081610bbfcd',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/flask_with_yaml/.env': '69153361d3fb50521ad5397496fcd63947516c9cb26283bb0cb7d69d3d64e612',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/format/.env': '987c3d50275cdb9d2e6823f5c1b88b14dbefd8306393d80d969de9498e96e873',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/full_test/.env': 'a33c054fd2411de64c598b95772568b0cb002030a779c0b4134a8f515b77a897',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/get_fresh/.env': '013f1cdd3bb493ecb44e6b7de45c12e49cd824549b60ce88675426506c92e1cb',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/ignore_unknown_envvars/.env': 'a095f1b4ee7ec5afd2b0c3460d2e6e2addeff92fd1915d8de2da335a1a69d92a',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/includes/.env': '8bdf408c5501870c23a73d95b9126bd1fd0f1cfea8df164815772c25ed692a68',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/inspect_load_file/.env': '64b306e5c39312aac90264977abd64595d958c3449c31d6a18357b400665719a',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/jenkins_secrets_file/.env': '6dd40a0c163bd54ea642e63b862fc4ccaa19985a77a4f6c46f287d3d4384fb6e',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/lower_read/.env': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/merge_enabled/.env': 'a7697a76bcaae02abc275224488fb26faa831557f4dde7a2e541b3aa0f5699ec',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/multiple_folders/.env': '1a1aa200b1b7a07eaa458850629cf2b00e3e6d764c23e9fd86a78d266dc016f1',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/multiple_sources/.env': 'd4f7af5f3402082ff774aad637160177d13f36969c1f36dcd075535e72ba00c7',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/new_merge/.env': '23f6540b77c6a73e90b853ec7038a4d6693daeb203c66e43f77ef4d6327b690c',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/overriding/.env': 'ed6d3329b9cc48f000b596a6a73ac2b02f57f6b7426bdd5e9152272cd372a5b8',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/project_root/.env': '52adfb8982be5c8de00b9f7235e2de524c7d5e47c7b726ee013ce90f3d7d9d0a',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/pytest_example_app/.env': '49005ce7e9f1f46c93b733a264d56cba7e4597fb4d903f01b73f3c9556adacc0',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/pytest_example_app/flask/.env': '49005ce7e9f1f46c93b733a264d56cba7e4597fb4d903f01b73f3c9556adacc0',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/redis_example/.env': '710efa7d556f1172ad51de9ee153847f90ee38327afda7cc0638c89623279998',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/settings_file/.env': '8ddf66fb8d7fa9e591b23ba1632f3ecb52b0d483c3cf3ce39b12032ebe68a109',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/simple/.env': 'e62ccfcf912f860db8cd4b8740c556d5c9bbad47a6dd6d4d3ee1262359f9f303',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/specific_settings_files/.env': '29b9e102a1e2b581dffb52c4e34f767e6d6e231cfc90b7f607ec4ff307814024',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/toml_with_secrets/.env': '0992caaadfe002b46e00273e92892011cc4ec9502d25431412ed279cacb89e42',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/validators_with_python/.env': '4437bd40a1d9bcd916663d5595994eab50ff1b3878c0fa6aa2ed672af23fb34f',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/validators_with_toml/.env': 'e62ccfcf912f860db8cd4b8740c556d5c9bbad47a6dd6d4d3ee1262359f9f303',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/vault/.env': '52405048c114c1aa8b0d36171e7d4edad25fdd4cf88aa2c60094679b94e4d288',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/vault_userpass/.env': '3bd6c1109997ef027781aed231b3df3294e8ffffbee912706ffdb4879cc9ddbf',
        'project_library/projects/dynaconf/seed/library/tests_functional/legacy/yaml_example_extra/.env': '0a32f4b57721bd92cffa3a6476f04a1d3a57256676bd8e743d9e45bf568cf5f9',
        'project_library/projects/dynaconf/seed/library/tests_functional/typed/insert/.env': '73b186119c0fa30eb8c78c657677b16c81a9a51cd787e01db16ecbd49fa9d3a2',
        'project_library/projects/dynaconf/seed/library/tests_functional/typed/multiple_env_prefixes/.env': '3791bbb81301bae0152fc29883f47819169c1fcfacb75aaa25b0012bdbfcf2ed',
        'project_library/projects/dynaconf/seed/library/tests_functional/typed/typed_with_dotenv_toml_secrets_validator_condition/.env': '732727f96268ea4f43da98dfe138190db42d511b0ec5e2a2c2452d4ead64132e',
        'project_library/projects/typer/seed/library/.env': '81b463a540ebc72b1d4afbc954d5247146344f986e7d842a82e032b7e08ecb2f',
        'project_library/projects/python-decouple/seed/library/tests/autoconfig/env/.env': '5b7f07de0fa0896faddd64c9f23966f5e0b611a3ff515beb3e2c82e3a2452a5b',
        'project_library/projects/python-decouple/seed/library/tests/autoconfig/env/custom-path/.env': 'b4eea58127083a24664bccf4cf4b278aca8804070a1384bf86ea4403c26af095',
        'project_library/projects/docutils/seed/library/sandbox/docutils_xml/global.log': 'e9152aa807000109164abc9e29fe616d28fa0c98c82e9321e8cb379cc914e515',
        'project_library/projects/docutils/seed/library/sandbox/docutils_xml/tag.log': '4865d24221a0494ced07cd65179bec1e913c90f0a4b73af7ae73241b104faaf7',
        'project_library/projects/docutils/seed/library/sandbox/odf2docutils/global.log': '4655300e0e8b1d7a26fc1208fb40be8f30c8aed07a362cbf26bd67a5890249eb',
        'project_library/projects/docutils/seed/library/sandbox/odf2docutils/tag.log': '09147df9ccd8e0cdd4ed3143310467058e6ac298803e1346ad8c674a6ef2ab9e',
        'project_library/projects/docutils/seed/library/sandbox/rst2beamer/feature_requests/alan_isaac_slides_test01_with_docinfo_docutils_v_0_8.log': '1aaf1f44ea4d019009663ec4b6f8c3a5d094a01d7a3f791e290a00a2c6dde7a2',
        'project_library/projects/docutils/seed/library/sandbox/rst2beamer/feature_requests/alan_isaac_slides_test01_without_beamer_visit_docinfo.log': '8f275578582bae45cc1d1227c094bbf36a3e995b0ce3c89d1e773b32de59b9d5',
        'project_library/projects/docutils/seed/library/sandbox/rst2beamer/feature_requests/alan_isaac_slides_test01_without_beamer_visit_docinfo_with_latex_docinfo.log': 'a613487a0960d43b2cfd9a9785349788fc1f432c653a47c9e9a190f4245796f8',
        'project_library/projects/docutils/seed/library/sandbox/rst2graph/global.log': 'fa363951035ff3ce3170fc241e6030144d20de49de488546a1e61c958f12f771',
        'project_library/projects/docutils/seed/library/sandbox/rst2graph/tag.log': 'd34558be7a4974d8049796e1059717aa325f6a07b31eb4522b5f9c46b608c2b9',
        'project_library/projects/docutils/seed/library/sandbox/rst2outline/global.log': '292a0ccddb53f5bf3fe72e1436c43d2a4ded4233cbfba06fe0a9253c67e0119b',
        'project_library/projects/docutils/seed/library/sandbox/rst2outline/tag.log': '463fdf1901ce0c9019170fbe4507649dd246f6f83e17a7c33db874be4a3ad578',
        'project_library/projects/docutils/seed/library/sandbox/rstdiff/global.log': '06c285535013062c9b3747934e31ed6b9c82b125cf621bff1524ebbe152d152e',
        'project_library/projects/docutils/seed/library/sandbox/rstdiff/tag.log': 'b35696f8d3b87e8bd1a197a622c8b0e2f4286a9f90b40eb007869d2dadbeed25',
        'project_library/projects/docutils/seed/library/sandbox/xml2rst/global.log': '3e26aa162b50e46e34c251731e7f62586c6c04b3cc6c6057f2276845f72aa642',
        'project_library/projects/docutils/seed/library/sandbox/xml2rst/tag.log': 'cd84655f263f61f47c6d6b0c17281c451ce9b98ee33b5682073dd585b65cea8e',
    }
    for relative, checksum in public_files.items():
        public = REPO / relative
        if resolved_directory == public.parent and public.name in ignored:
            if public.is_symlink() or hashlib.sha256(public.read_bytes()).hexdigest() != checksum:
                raise ValueError('固定上游公开文件摘要不符')
            ignored.remove(public.name)
    # 这两处target是固定Git跟踪的测试期望原件，完整清单约束防止放进本地构建产物。
    public_directories = {
        'project_library/projects/docutils/seed/library/sandbox/odf2docutils/tests/presentationSimple/target': '00807434398b437e1b5a6afda90894fe3d13d7e7f4e424fcec06ee25fce61b27',
        'project_library/projects/docutils/seed/library/sandbox/odf2docutils/tests/textSimple/target': 'bf69411b21f4630b72ca45b23da31db1ece7068f839e76167fef3ba807d494a6',
    }
    for relative, checksum in public_directories.items():
        public = REPO / relative
        if resolved_directory == public.parent and public.name in ignored:
            if _public_source_directory_digest(public) != checksum:
                raise ValueError('固定上游夹具目录摘要不符')
            ignored.remove(public.name)
    return ignored


def restore_upstream_checkout_bytes(root: Path) -> list[str]:
    """在交付副本中恢复已核上游 Git 行尾转换，保留固定源码 blob 的原始字节。

    :param root: 完整源码副本根；调用者不得传入生产数据目录。
    :return: 本次实际恢复的相对路径；未知内容或链接拒绝，不泛化转换其它文件。
    """
    originals = {
        'project_library/projects/python-dateutil/seed/library/NEWS': (
            '9e3ee1f3d960cc0cf7e823abb665cc43fc879330e175b8267a3b5cdc5627a3c5',
            '2619c43f820d1f8f8cf3c2ad698ceaf2529baf88482a83164471d9f4d00d6a6e'),
        'project_library/projects/python-dateutil/seed/library/docs/make.bat': (
            'd853adea8f9e9c2b5e67a443114b4e940764d1856a104ff3e79598212c73a0b7',
            '85cb8f97fa68e42e6bf11747fae73a7ed0a52a4cfb98d9909d4ba91e41b8cd4a'),
    }
    pending = []
    for relative, (original_sha, checkout_sha) in originals.items():
        path = root / relative
        if root.is_symlink() or path.is_symlink():
            raise ValueError('固定上游行尾原件不能是链接')
        if any((root / parent).is_symlink() for parent in Path(relative).parents):
            raise ValueError('固定上游行尾原件不能沿父目录链接读取')
        if not path.exists():
            continue
        if not path.is_file():
            raise ValueError('固定上游行尾原件必须是普通文件')
        content = path.read_bytes()
        checksum = hashlib.sha256(content).hexdigest()
        if checksum == original_sha:
            continue
        # 上游属性显式指定 CRLF；只接受完整文件的已核转换结果，不能掩盖源码修改。
        restored = content.replace(b'\r\n', b'\n')
        if checksum != checkout_sha or hashlib.sha256(restored).hexdigest() != original_sha:
            raise ValueError('固定上游行尾原件摘要不符：' + relative)
        pending.append((relative, path, restored))
    # 全部校验后才写本次副本；拒绝后一文件时不会留下部分恢复。
    for _, path, restored in pending:
        path.write_bytes(restored)
    return [relative for relative, _, _ in pending]


def build(release: str, manifest_path: Path) -> None:
    """构建两个最终镜像，完成后生成可核对的联合清单。

    :param release: 仅用于 v3 的唯一批次名
    :param manifest_path: 新清单路径
    :return: None
    """
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", release):
        raise ValueError("批次名不合法")
    parent = command("git", "rev-parse", "HEAD", capture=True).strip()
    gateway = command("git", "-C", "cc2api", "rev-parse", "HEAD", capture=True).strip()
    dirty = bool(command("git", "status", "--porcelain", capture=True).strip())
    if manifest_path.exists():
        raise ValueError("版本清单已经存在，禁止覆盖批次")
    with tempfile.TemporaryDirectory(prefix="vibebench-v3-source-") as temporary:
        snapshot = Path(temporary)
        folders = ("cc2api/src", "cc2api/vendor", "cc2api/craftls", "cc2api/web", "images/account",
            "images/sidecar", "images/worker", "images/v3", "orchestrator", "webui", "project_library")
        for relative in folders:
            shutil.copytree(REPO / relative, snapshot / relative, ignore=source_snapshot_ignore)
        for relative in ("cc2api/Cargo.toml", "cc2api/Cargo.lock", "topics.md"):
            (snapshot / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / relative, snapshot / relative)
        restore_upstream_checkout_bytes(snapshot)
        digest = hashlib.sha256()
        for path in sorted(item for item in snapshot.rglob("*") if item.is_file()):
            digest.update(str(path.relative_to(snapshot)).encode())
            digest.update(b"\0")
            digest.update(hashlib.sha256(path.read_bytes()).digest())
        source_hash = digest.hexdigest()
        images = {}
        for role in ("control", "account"):
            reference = f"vibebench-v3-{role}:v3-{release}"
            if subprocess.run(["docker", "image", "inspect", reference], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
                raise ValueError("批次镜像标签已经存在，禁止覆盖")
            command("docker", "build", "-f", str(snapshot / "images/v3/Dockerfile"), "--target", role,
                "--build-arg", f"V3_RELEASE={release}", "--build-arg", f"V3_PARENT_REV={parent}",
                "--build-arg", f"V3_GATEWAY_REV={gateway}", "-t", reference, str(snapshot))
            info = json.loads(command("docker", "image", "inspect", reference, capture=True))[0]
            images[role] = {"reference": reference, "digest": info["Id"],
                "config_digest": _image_config_digest(reference),
                "platform": info["Os"] + "/" + info["Architecture"]}
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("x") as output:
        json.dump({"schema": 3, "bridge_protocol": 1, "layout_version": 2, "default_cli_version": "2.1.293",
            "release": release, "parent_revision": parent, "gateway_revision": gateway,
            "dirty_worktree": dirty, "source_content_sha256": source_hash, "images": images}, output, indent=2)
        output.write("\n")


def _manifest_values(manifest_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text())
    return {"V3_RELEASE_MANIFEST": str(manifest_path),
        **{f"V3_{role.upper()}_IMAGE": manifest["images"][role]["reference"] for role in ("control", "account")}}


def _write_new_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as output:
            json.dump(value, output, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        # link 以独占方式发布完整文件；不能用 replace 覆盖另一个已完成批次。
        os.link(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _image_config_digest(reference: str) -> str:
    # containerd 的 Id 可以是 OCI 索引；归档中的原始 config 字节才有跨 daemon 的稳定哈希。
    process = subprocess.Popen(["docker", "save", reference], cwd=REPO, stdout=subprocess.PIPE)
    configs, manifests = {}, []
    try:
        with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
            for item in archive:
                if not item.isfile() or item.size > 4 * 1024**2:
                    continue
                if item.name == "manifest.json":
                    manifests = json.load(archive.extractfile(item))
                elif item.name.endswith(".json") or item.name.startswith("blobs/sha256/"):
                    payload = archive.extractfile(item).read()
                    try:
                        value = json.loads(payload)
                    except (ValueError, UnicodeDecodeError):
                        continue
                    if isinstance(value, dict) and isinstance(value.get("rootfs"), dict) and "architecture" in value:
                        configs[item.name] = "sha256:" + hashlib.sha256(payload).hexdigest()
        if process.wait() != 0:
            raise ValueError("镜像配置归档导出失败")
        entries = [item for item in manifests if reference in (item.get("RepoTags") or [])]
        if len(entries) != 1 or entries[0].get("Config") not in configs:
            raise ValueError("无法从镜像归档核对唯一的原始配置")
        return configs[entries[0]["Config"]]
    except tarfile.TarError as error:
        raise ValueError("镜像配置归档格式不匹配") from error
    finally:
        process.stdout.close()
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def _image_matches(info: dict, entry: dict) -> bool:
    if info["Id"] == entry["digest"]:
        return True
    config = entry.get("config_digest")
    if not config or not re.fullmatch(r"sha256:[0-9a-f]{64}", config):
        return False
    # classic store 用 config ID，containerd 可用 OCI 索引 ID；两者均由发布清单固定。
    registry = entry.get("registry_digest")
    return info["Id"] == config or bool(registry and (
        info["Id"] == registry or (info.get("Descriptor") or {}).get("digest") == registry))


def _local_image_matches(reference: str, info: dict, entry: dict) -> bool:
    """核对本地镜像；containerd 导入 archive 时允许以原始 config 证明同一内容。

    :param reference: 当前本地镜像引用
    :param info: `docker image inspect` 的单条结果
    :param entry: 发布清单中的角色镜像记录
    :return: 本地镜像可由清单 digest 或 archive 原始 config 唯一确认时为 True
    """
    if _image_matches(info, entry):
        return True
    descriptor = info.get("Descriptor") or {}
    config = entry.get("config_digest")
    # 只有 containerd 从 docker archive 重建 OCI manifest 的已知形态才做昂贵回查；
    # config digest 同时锚定 rootfs diff_ids 和运行配置，不能只凭标签放行。
    if (descriptor.get("mediaType") != "application/vnd.oci.image.manifest.v1+json"
            or not config or not re.fullmatch(r"sha256:[0-9a-f]{64}", config)):
        return False
    try:
        return _image_config_digest(reference) == config
    except (ValueError, OSError, subprocess.CalledProcessError):
        return False


def _container_image_matches(image_id: str, local_id: str, entry: dict) -> bool:
    """核对容器镜像是否属于当前已验证的本地标签或发布清单。

    :param image_id: 容器 inspect 返回的镜像 ID
    :param local_id: 当前批次标签经严格校验后的本地镜像 ID
    :param entry: 发布清单中的角色镜像记录
    :return: 容器使用当前本地内容或清单固定 digest 时为 True
    """
    return image_id == local_id or _image_matches({"Id": image_id}, entry)


def _check_local_reference(reference: str, expected: dict) -> None:
    result = subprocess.run(["docker", "image", "inspect", reference], cwd=REPO,
        capture_output=True, text=True, check=False)
    if result.returncode == 0:
        if not _local_image_matches(reference, json.loads(result.stdout)[0], expected):
            raise ValueError("本地批次标签指向其它镜像，拒绝覆盖")
    elif "No such image" not in result.stderr:
        raise ValueError("无法核对本地镜像，拒绝继续")


def publish(manifest_path: Path, output_path: Path, bundle_path: Path,
            namespace: str = "ghcr.io/silentflower") -> dict:
    """将当前 v3 Action 的同批镜像发布到 GHCR，最后才生成完整交付清单。

    :param manifest_path: 已完成构建的本地清单
    :param output_path: 全新发布清单路径
    :param bundle_path: 全新同批镜像包路径
    :param namespace: 当前 Action 仓库 owner 的 GHCR namespace
    :return: 已发布的联合清单；失败保留发布标记，必须使用新 attempt 重跑
    """
    manifest = json.loads(manifest_path.read_text())
    expected_release = "ci-" + os.environ.get("GITHUB_RUN_ID", "") + "-" + os.environ.get("GITHUB_RUN_ATTEMPT", "")
    owner = os.environ.get("GITHUB_REPOSITORY_OWNER", "").lower()
    if (os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("GITHUB_REF") != "refs/heads/v3"
            or not re.fullmatch(r"ci-[1-9][0-9]*-[1-9][0-9]*", expected_release)
            or manifest.get("release") != expected_release
            or manifest.get("parent_revision") != os.environ.get("GITHUB_SHA")
            or os.environ.get("GITHUB_REPOSITORY", "").lower() != owner + "/vibecoding-bench"
            or namespace != "ghcr.io/" + owner or not re.fullmatch(r"ghcr.io/[a-z0-9][a-z0-9-]*", namespace)):
        raise ValueError("发布必须使用当前 v3 Action 的仓库、提交与唯一 run/attempt 批次")
    if manifest.get("dirty_worktree") is not False:
        raise ValueError("不能发布含未提交修改或来源未知的批次")
    paths = [manifest_path.resolve(), output_path.resolve(), bundle_path.resolve()]
    if len(set(paths)) != 3 or output_path.exists() or bundle_path.exists():
        raise ValueError("发布清单和镜像包必须使用全新独立路径")
    started = output_path.with_name(output_path.name + ".started")
    if started.exists():
        raise ValueError("本批次已经开始发布，请使用新的 Action attempt 重跑")
    inspect_images(_manifest_values(manifest_path))
    references = {role: f"{namespace}/vibebench-v3-{role}:v3-{manifest['release']}" for role in ("control", "account")}
    for role, reference in references.items():
        _check_local_reference(reference, manifest["images"][role])
    # GitHub 重跑增加 attempt；本次标记防止进程重试复用同批标签覆盖部分发布。
    _write_new_json(started,
        {"release": manifest["release"], "parent_revision": manifest["parent_revision"]})
    published = {**manifest, "images": {}}
    for role, reference in references.items():
        entry = manifest["images"][role]
        command("docker", "tag", entry["reference"], reference)
        command("docker", "push", reference)
        info = json.loads(command("docker", "image", "inspect", reference, capture=True))[0]
        repository = reference.rsplit(":", 1)[0]
        digests = {value[len(repository) + 1:] for value in info.get("RepoDigests", [])
            if value.startswith(repository + "@")}
        if info["Id"] != entry["digest"] or len(digests) != 1 or not re.fullmatch(r"sha256:[0-9a-f]{64}", next(iter(digests), "")):
            raise ValueError("推送后镜像配置 ID 或仓库 digest 无法核对")
        config_digest = entry.get("config_digest") or _image_config_digest(entry["reference"])
        published["images"][role] = {**entry, "reference": reference,
            "config_digest": config_digest, "registry_digest": next(iter(digests))}
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=bundle_path.name + ".", dir=bundle_path.parent)
    process = None
    try:
        with os.fdopen(descriptor, "wb") as output:
            process = subprocess.Popen(["docker", "save", *references.values()], cwd=REPO, stdout=subprocess.PIPE)
            try:
                with gzip.GzipFile(fileobj=output, mode="wb", mtime=0) as archive:
                    shutil.copyfileobj(process.stdout, archive, length=1024 * 1024)
                if process.wait() != 0:
                    raise ValueError("同批镜像包生成失败")
                output.flush()
                os.fsync(output.fileno())
            finally:
                process.stdout.close()
                if process.poll() is None:
                    process.terminate()
                    process.wait()
        os.link(temporary, bundle_path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    published["bundle"] = {"name": bundle_path.name, "sha256": _file_sha256(bundle_path), "size": bundle_path.stat().st_size}
    _write_new_json(output_path, published)
    return published


def _published_manifest(manifest_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema") != 3 or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", manifest.get("release", "")):
        raise ValueError("发布清单格式或批次不匹配")
    for role in ("control", "account"):
        entry = manifest["images"][role]
        reference = entry["reference"]
        if not re.fullmatch(r"ghcr.io/[a-z0-9][a-z0-9-]*/vibebench-v3-" + role + ":v3-" + re.escape(manifest["release"]), reference):
            raise ValueError("发布镜像引用不属于指定 v3 角色和批次")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", entry.get("registry_digest", "")):
            raise ValueError("发布清单缺少有效仓库 digest")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", entry.get("digest", "")):
            raise ValueError("发布清单缺少有效本地镜像 ID")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", entry.get("config_digest", "")):
            raise ValueError("发布清单缺少有效原始配置 digest")
    return manifest


def pull(manifest_path: Path) -> None:
    """按仓库 digest 下载两镜像，核对后建立受控批次标签。

    :param manifest_path: 完整的发布清单
    :return: None；认证、下载或身份核对失败时停止
    """
    manifest = _published_manifest(manifest_path)
    for role in ("control", "account"):
        entry = manifest["images"][role]
        reference = entry["reference"]
        _check_local_reference(reference, entry)
    for role in ("control", "account"):
        entry = manifest["images"][role]
        pinned = entry["reference"].rsplit(":", 1)[0] + "@" + entry["registry_digest"]
        command("docker", "pull", pinned)
        info = json.loads(command("docker", "image", "inspect", pinned, capture=True))[0]
        if not _local_image_matches(pinned, info, entry):
            raise ValueError("下载镜像配置 ID 与发布清单不匹配")
        command("docker", "tag", pinned, entry["reference"])
    inspect_images(_manifest_values(manifest_path))


def load_bundle(manifest_path: Path, bundle_path: Path) -> None:
    """验证同批包的 SHA256 后加载，不需要服务器保存仓库凭据。

    :param manifest_path: 完整发布清单
    :param bundle_path: 与清单匹配的压缩镜像包
    :return: None；包或镜像身份不符时停止
    """
    manifest = _published_manifest(manifest_path)
    bundle = manifest.get("bundle") or {}
    if (bundle.get("name") != bundle_path.name or bundle.get("size") != bundle_path.stat().st_size
            or not re.fullmatch(r"[0-9a-f]{64}", bundle.get("sha256", ""))
            or _file_sha256(bundle_path) != bundle["sha256"]):
        raise ValueError("同批镜像包名称、大小或 SHA256 不匹配")
    for role in ("control", "account"):
        entry = manifest["images"][role]
        _check_local_reference(entry["reference"], entry)
    command("docker", "load", "--input", str(bundle_path))
    inspect_images(_manifest_values(manifest_path))


def _owned_root(values: dict, stopped: bool = False) -> Path:
    deployment = values["V3_DEPLOYMENT_ID"]
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,35}", deployment):
        raise ValueError("部署标识不合法")
    configured = Path(values["V3_DATA_ROOT"])
    root = configured.resolve()
    if not configured.is_absolute() or configured != root:
        raise ValueError("数据根必须为非链接的绝对路径")
    marker = root / ".v3-deployment.json"
    if not marker.is_file() or json.loads(marker.read_text()).get("deployment") != deployment:
        raise ValueError("数据目录归属不匹配")
    if stopped and command("docker", "ps", "-q", "--filter", "label=vibebench.product=v3",
            "--filter", f"label=vibebench.deployment={deployment}", capture=True).strip():
        raise ValueError("请先 stop 本部署")
    return root


def status(values: dict) -> dict:
    """展示本部署全部容器、账号占用和实际镜像 ID，不输出服务秘密。

    :param values: 当前部署配置
    :return: 只读状态摘要，同时以 JSON 打印
    """
    manifest = inspect_images(values)
    root = _owned_root(values)
    local_ids = {}
    for role in ("control", "account"):
        reference = values.get(f"V3_{role.upper()}_IMAGE") or manifest["images"][role].get("reference")
        local_ids[role] = (json.loads(command("docker", "image", "inspect", reference, capture=True))[0]["Id"]
            if reference else manifest["images"][role]["digest"])
    ids = command("docker", "ps", "-aq", "--filter", "label=vibebench.product=v3",
        "--filter", f"label=vibebench.deployment={values['V3_DEPLOYMENT_ID']}", capture=True).split()
    inspected = json.loads(command("docker", "inspect", *ids, capture=True)) if ids else []
    containers = []
    for item in inspected:
        labels = item["Config"].get("Labels") or {}
        if labels.get("vibebench.product") != "v3" or labels.get("vibebench.deployment") != values["V3_DEPLOYMENT_ID"]:
            continue
        role = labels.get("vibebench.role", "unknown")
        expected_role = "account" if role in ("account", "account-sender", "account-network") else "control"
        expected = manifest["images"][expected_role]
        containers.append({"id": item["Id"], "name": item["Name"].lstrip("/"), "role": role,
            "environment_id": labels.get("vibebench.environment"), "status": item["State"]["Status"],
            "image_digest": item["Image"],
            "matches_release": _container_image_matches(item["Image"], local_ids[expected_role], expected)})
    environments = []
    database = root / "bench/db.sqlite"
    if database.is_file():
        if not database.resolve().is_relative_to(root):
            raise ValueError("数据库路径不属于本部署")
        with sqlite3.connect("file:" + quote(str(database), safe="/") + "?mode=ro", uri=True) as connection:
            connection.row_factory = sqlite3.Row
            if connection.execute("SELECT 1 FROM sqlite_master WHERE name='account_environments'").fetchone():
                columns = {row[1] for row in connection.execute("PRAGMA table_info(account_environments)")}
                extra = "".join(",e." + name for name in ("isolation_version", "network_container_id", "sender_container_id") if name in columns)
                environments = [dict(row) for row in connection.execute("SELECT e.environment_id,e.name,e.account_id,e.generation,e.container_id,e.state,a.cc2api_account_id" + extra + " FROM account_environments e LEFT JOIN accounts a ON a.id=e.account_id ORDER BY e.name")]
    host = values.get("V3_BIND_ADDRESS", "127.0.0.1")
    if host == "0.0.0.0":
        host = "127.0.0.1"
    for environment in environments:
        container = next((item for item in containers if item["id"] == environment["container_id"]), None)
        environment["container_status"] = container["status"] if container else "missing"
        environment["image_digest"] = container["image_digest"] if container else None
        environment["roles"] = {role: next(({"status": item["status"], "matches_release": item["matches_release"]}
            for item in containers if item["id"] == environment.get(column)), {"status": "missing", "matches_release": False})
            for role, column in (("cli", "container_id"), ("network", "network_container_id"), ("sender", "sender_container_id"))}
        environment["occupancy"] = {"active": None, "waiting": None, "lease": None, "available": False}
        account_id = environment.pop("cc2api_account_id")
        if account_id is not None:
            request = urllib.request.Request(f"http://{host}:{values.get('V3_HOST_PORT', '18080')}/admin/runtime/accounts/{int(account_id)}/lease",
                headers={"Authorization": "Bearer " + values["V3_ADMIN_PASSWORD"]})
            try:
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with opener.open(request, timeout=2) as response:
                    snapshot = json.loads(response.read(65536))
                lease = snapshot.get("lease")
                environment["occupancy"] = {"active": snapshot["active"], "waiting": snapshot.get("waiting", 0),
                    "lease": {key: lease.get(key) for key in ("owner", "generation", "phase", "expires_at")} if lease else None, "available": True}
                environment["occupancy"]["holders"] = [{key: holder.get(key) for key in
                    ("owner", "generation", "phase", "expires_at", "shared_cli")}
                    for holder in snapshot.get("holders", [lease] if lease else [])]
                environment["occupancy"]["cli_capacity"] = snapshot.get("cli_capacity", 1)
            except (OSError, ValueError, KeyError):
                pass
        else:
            environment["occupancy"] = {"active": 0, "waiting": 0, "lease": None, "available": True}
        if re.fullmatch(r"[a-f0-9]{32}", environment["environment_id"]):
            execution = root / "bench/environments" / environment["environment_id"] / "runtime/execution.json"
            if execution.is_file() and execution.resolve().is_relative_to(root):
                proof = json.loads(execution.read_text())
                environment["execution"] = {key: proof.get(key) for key in ("source", "phase")}
            records = execution.parent / "executions"
            if records.is_symlink():
                raise ValueError("共享执行登记目录不能是链接")
            environment["executions"] = []
            for record in sorted(records.glob("*.json")):
                if record.is_symlink() or not record.resolve().is_relative_to(root) or record.stat().st_size > 65536:
                    raise ValueError("共享执行登记路径或大小无效")
                proof = json.loads(record.read_text())
                environment["executions"].append({key: proof.get(key) for key in ("source", "phase", "run_id", "shared_cli")})
    result = {"deployment": values["V3_DEPLOYMENT_ID"], "release": manifest["release"],
        "images": manifest["images"], "containers": containers, "environments": environments}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def import_offline(values: dict, source: Path, apply: bool = False) -> dict:
    """在停机的独立 v3 库导入白名单历史元数据，默认只演练并回滚。

    :param values: 当前部署配置
    :param source: 去凭据 JSON；不接收代理、profile、正文、AT 或 RT
    :param apply: 显式保存元数据；所有账号保持停用且不建立上游绑定
    :return: 创建与幂等跳过数量，不包含来源记录正文
    """
    root = _owned_root(values, stopped=True)
    if source.stat().st_size > 1024 * 1024:
        raise ValueError("离线资料超过大小上限")
    payload = json.loads(source.read_text())
    if not isinstance(payload, dict) or set(payload) != {"schema", "source_id", "accounts", "tasks", "runs"} or type(payload["schema"]) is not int or payload["schema"] != 1:
        raise ValueError("离线资料格式不匹配")
    source_id = payload["source_id"]
    if not isinstance(source_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", source_id):
        raise ValueError("离线来源标识无效")
    contracts = {"accounts": ({"legacy_id", "name"}, {"enabled", "deleted"}),
        "tasks": ({"legacy_id", "account_legacy_id", "topic_no", "title"}, set()),
        "runs": ({"id", "task_legacy_id", "account_legacy_id", "status"}, set())}
    for kind, (required, optional) in contracts.items():
        records = payload[kind]
        if not isinstance(records, list):
            raise ValueError("离线记录必须为列表")
        identifiers = set()
        for record in records:
            if not isinstance(record, dict) or not required <= set(record) or set(record) - required - optional:
                raise ValueError("离线记录包含未允许字段；凭据、代理和正文不能导入")
            for key, value in record.items():
                if key in ("legacy_id", "id", "name", "task_legacy_id", "account_legacy_id"):
                    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
                        raise ValueError("离线记录标识无效")
                elif key in ("enabled", "deleted") and type(value) is not bool:
                    raise ValueError("离线启停状态必须为布尔值")
                elif key == "topic_no" and (type(value) is not int or value < 1):
                    raise ValueError("离线题号必须为正整数")
                elif key == "title" and (not isinstance(value, str) or len(value) > 500):
                    raise ValueError("离线标题无效")
                elif key == "status" and value not in ("done", "failed", "stopped", "queued", "running", "stopping", "quota_wait"):
                    raise ValueError("离线运行状态无效")
            identifier = record["id" if kind == "runs" else "legacy_id"]
            if identifier in identifiers:
                raise ValueError("离线记录标识重复")
            identifiers.add(identifier)
    database = root / "bench/db.sqlite"
    if not database.is_file() or not database.resolve().is_relative_to(root):
        raise ValueError("请先初始化并停止本部署，数据库必须属于 v3")
    counts = {"created": 0, "skipped": 0, "dry_run": not apply}
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    mapping = {}
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("CREATE TABLE IF NOT EXISTS v3_offline_imports(source_id TEXT,kind TEXT,legacy_id TEXT,digest TEXT NOT NULL,target_id TEXT NOT NULL,PRIMARY KEY(source_id,kind,legacy_id))")
        for kind in contracts:
            for record in payload[kind]:
                legacy_id = record["id" if kind == "runs" else "legacy_id"]
                digest = hashlib.sha256(json.dumps(record, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                existing = connection.execute("SELECT digest,target_id FROM v3_offline_imports WHERE source_id=? AND kind=? AND legacy_id=?", (source_id, kind, legacy_id)).fetchone()
                if existing:
                    if existing["digest"] != digest:
                        raise ValueError("离线记录已导入但内容改变，拒绝覆盖")
                    target_id = existing["target_id"]
                    counts["skipped"] += 1
                elif kind == "accounts":
                    if connection.execute("SELECT 1 FROM accounts WHERE name=?", (record["name"],)).fetchone():
                        raise ValueError("账号名已存在且不属于本次离线来源，拒绝接管")
                    cursor = connection.execute("INSERT INTO accounts(name,profile_path,enabled,warmup_enabled,deleted_at) VALUES(?,?,0,0,?)",
                        (record["name"], "/data/profiles/" + record["name"], time.time() if record.get("deleted") else None))
                    target_id = str(cursor.lastrowid)
                    counts["created"] += 1
                elif kind == "tasks":
                    account_id = mapping.get(("accounts", record["account_legacy_id"]))
                    if not account_id:
                        raise ValueError("历史任务缺少本来源账号")
                    cursor = connection.execute("INSERT INTO tasks(topic_no,title,prompt,account_id,status,deleted_at) VALUES(?,?,'',?,'archived',?)",
                        (record["topic_no"], record["title"], int(account_id), time.time()))
                    target_id = str(cursor.lastrowid)
                    counts["created"] += 1
                else:
                    account_id = mapping.get(("accounts", record["account_legacy_id"]))
                    task_id = mapping.get(("tasks", record["task_legacy_id"]))
                    if not account_id or not task_id:
                        raise ValueError("历史运行缺少本来源任务或账号")
                    task_account = connection.execute("SELECT account_id FROM tasks WHERE id=?", (int(task_id),)).fetchone()
                    if task_account["account_id"] != int(account_id):
                        raise ValueError("历史任务与运行账号归属不一致")
                    run_status = record["status"] if record["status"] in ("done", "failed", "stopped") else "stopped"
                    connection.execute("INSERT INTO runs(id,task_id,account_id,status) VALUES(?,?,?,?)", (record["id"], int(task_id), int(account_id), run_status))
                    target_id = record["id"]
                    counts["created"] += 1
                mapping[kind, legacy_id] = target_id
                if not existing:
                    connection.execute("INSERT INTO v3_offline_imports VALUES(?,?,?,?,?)", (source_id, kind, legacy_id, digest, target_id))
        if apply:
            connection.commit()
        else:
            connection.rollback()
    finally:
        connection.close()
    return counts


def _prune_previous_backups(target: Path, deployment: str, root: Path) -> int:
    removed = 0
    for candidate in target.parent.iterdir():
        if candidate==target or candidate.is_symlink() or not candidate.is_dir():
            continue
        marker = candidate/'.v3-backup.json'
        release = candidate/'release.json'
        data = candidate/'data'
        try:
            if (any(path.is_symlink() or not path.is_file() or path.stat().st_size>65536 for path in (marker,release))
                    or data.is_symlink() or not data.is_dir()):
                continue
            record = json.loads(marker.read_text())
            manifest = json.loads(release.read_text())
            owner_path = data/'.v3-deployment.json'
            if owner_path.is_symlink() or not owner_path.is_file() or owner_path.stat().st_size>65536:
                continue
            owner = json.loads(owner_path.read_text())
            if (record.get('deployment')!=deployment or record.get('source_root')!=str(root)
                    or owner.get('deployment')!=deployment or manifest.get('release')!=record.get('release')
                    or manifest.get('layout_version')!=record.get('layout_version')
                    or manifest.get('bridge_protocol')!=record.get('bridge_protocol')):
                continue
        except (OSError,ValueError,TypeError,AttributeError):
            # 未知、未完成或跨部署目录不属于自动轮换范围。
            continue
        shutil.rmtree(candidate)
        removed += 1
    return removed


def backup(values: dict, destination: Path) -> None:
    """仅在本部署全部停止后保存持久目录和一致的 SQLite 快照。

    :param values: 当前部署配置
    :param destination: 全新且与数据根分离的绝对备份目录
    :return: None；新备份校验成功后只保留同目录、同部署及同数据根的本次备份。
    """
    deployment = values["V3_DEPLOYMENT_ID"]
    root = _owned_root(values, stopped=True)
    target = destination.resolve()
    if not destination.is_absolute() or target.exists() or target == root or root in target.parents or target in root.parents:
        raise ValueError("备份必须使用数据根以外的全新绝对目录")
    manifest = inspect_images(values)
    target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    lock_name = '.v3-backup-'+hashlib.sha256((deployment+':'+str(root)).encode()).hexdigest()[:20]+'.lock'
    descriptor = os.open(target.parent/lock_name,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        if not S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError('备份锁必须为普通文件')
        try:
            fcntl.flock(descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError('本部署已有备份操作进行中') from error
        target.mkdir(mode=0o700)
        try:
            # tmux 留下的 Unix socket 无法复制或恢复连接；持久文件和符号链接仍完整保留。
            shutil.copytree(root, target / "data", symlinks=True,
                ignore=lambda directory, names: [name for name in names
                    if S_ISSOCK((Path(directory) / name).lstat().st_mode)])
            for relative in ("gateway/gateway.sqlite", "bench/db.sqlite"):
                source = root / relative
                if not source.exists():
                    continue
                output = target / "data" / relative
                for suffix in ("", "-wal", "-shm"):
                    Path(str(output) + suffix).unlink(missing_ok=True)
                # 使用 SQLite backup API 而非只复制主文件，保留尚未 checkpoint 的合法事务。
                with sqlite3.connect("file:" + quote(str(source), safe="/") + "?mode=ro", uri=True) as current:
                    with sqlite3.connect(output) as snapshot:
                        current.backup(snapshot)
                        if snapshot.execute('PRAGMA quick_check').fetchall()!=[('ok',)]:
                            raise ValueError('备份数据库完整性检查未通过')
                output.chmod(0o600)
            (target / "release.json").write_text(json.dumps(manifest, indent=2) + "\n")
            marker = target/".v3-backup.json"
            with marker.open('x') as stream:
                json.dump({"deployment":deployment,"source_root":str(root),"layout_version":manifest["layout_version"],
                    "bridge_protocol":manifest["bridge_protocol"],"release":manifest["release"],"completed_at":time.time()},stream)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            shutil.rmtree(target)
            raise
        # 必须在新快照完成后才淘汰旧副本；轮换失败也不能删除刚完成的恢复点。
        removed = _prune_previous_backups(target,deployment,root)
        print('v3 停机备份完成：'+str(target)+'；保留最近 1 份，已移除旧备份 '+str(removed)+' 份')
    finally:
        os.close(descriptor)


def main() -> None:
    """执行指定操作；stop 只收口匹配 v3 标签的账号和 Compose 服务。

    :return: None
    """
    parser = argparse.ArgumentParser(description="v3 联合镜像管理")
    parser.add_argument("action", choices=("build", "publish", "pull", "load", "check", "up", "status", "stop", "backup", "import-offline"))
    parser.add_argument("--env", type=Path)
    parser.add_argument("--release")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--namespace", default="ghcr.io/silentflower")
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.action == "build":
        build(args.release or uuid.uuid4().hex, args.manifest or REPO / "releases" / "v3.json")
        return
    if args.action in ("publish", "pull", "load"):
        if not args.manifest:
            parser.error("镜像交付操作需要 --manifest")
        if args.action == "publish":
            if not args.output or not args.bundle:
                parser.error("publish 需要 --output 和 --bundle")
            publish(args.manifest, args.output, args.bundle, args.namespace)
        elif args.action == "pull":
            pull(args.manifest)
        else:
            if not args.bundle:
                parser.error("load 需要 --bundle")
            load_bundle(args.manifest, args.bundle)
        return
    if not args.env:
        parser.error("此操作需要 --env")
    values = load_environment(args.env)
    if args.action == "import-offline":
        if not args.source:
            parser.error("import-offline 需要 --source")
        print(json.dumps(import_offline(values, args.source, args.apply), ensure_ascii=False))
        return
    if args.action == "backup":
        if not args.backup_dir:
            parser.error("backup 需要 --backup-dir")
        backup(values, args.backup_dir)
        return
    environment = dict(os.environ, **values)
    compose = ["docker", "compose", "--env-file", str(args.env.resolve()), "-f", str(COMPOSE)]
    if args.action in ("check", "up"):
        root = preflight(values)
        if args.action == "check":
            print("v3 版本、数据归属、端口和资源预检通过")
            return
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        for child in ("gateway", "bench"):
            (root / child).mkdir(exist_ok=True, mode=0o700)
        (root / ".v3-deployment.json").write_text(json.dumps({"deployment": values["V3_DEPLOYMENT_ID"]}))
        environment.update(values)
        command(*compose, "up", "-d", environment=environment)
    elif args.action == "status":
        status(values)
    else:
        deployment = values["V3_DEPLOYMENT_ID"]
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,35}", deployment):
            raise ValueError("部署标识不合法")
        # 调度器先收口 CLI 租约，此时网关仍可用；随后关闭发送器和网关。
        # 只认产品/部署/角色标签，不通过 Compose 项目名接管其它容器。
        for role in ("orchestrator", "account", "account-sender", "account-network", "gateway"):
            ids = command("docker", "ps", "-q", "--filter", "label=vibebench.product=v3",
                "--filter", f"label=vibebench.deployment={deployment}",
                "--filter", f"label=vibebench.role={role}", capture=True).split()
            if ids:
                command("docker", "stop", *ids)
        # 不删除网络：已停止的固定账号容器仍引用该网络；数据和容器均保留。


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        detail = str(error) if isinstance(error, ValueError) else type(error).__name__
        print(f"v3 操作失败：{detail}", file=sys.stderr)
        sys.exit(1)
