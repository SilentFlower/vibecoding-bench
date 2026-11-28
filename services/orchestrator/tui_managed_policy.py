"""读取节点管理员发布、绑定到单个账号环境的 Claude Code 管理策略。"""

import fcntl
from hashlib import sha256
import json
import os
from os import stat_result
from pathlib import Path
import re
from stat import S_ISDIR, S_ISREG
from tempfile import TemporaryDirectory

from runtime_files import atomic_text, directory_fd
from system_update_contract import safe_read, strict_json


POLICY_DIRECTORY = 'tui-managed-policies'
DEFAULT_POLICY_DIRECTORY = 'tui-direct-policy'
DEFAULT_DIRECT_LABEL = 'vibebench.tui-direct-default'
DEFAULT_MOD = Path(__file__).with_name('tui-direct-mod')
MANAGED_SETTINGS_PATH = '/etc/claude-code/managed-settings.json'
MANAGED_MARKETPLACE_PATH = '/opt/flower/managed-plugins'


def _trusted(path: Path, *, directory: bool | None = None, sender_readable: bool = False) -> stat_result:
    info = path.lstat()
    is_directory = S_ISDIR(info.st_mode)
    if ((directory is not None and directory != is_directory)
            or (not is_directory and (not S_ISREG(info.st_mode) or info.st_nlink != 1))
            or info.st_uid != 0 or info.st_mode & 0o022):
        raise ValueError('Claude 托管策略必须使用管理员拥有的目录和普通文件')
    if sender_readable:
        access = 0o5 if is_directory else 0o4
        if info.st_mode & access != access and (info.st_gid != 1001 or (info.st_mode >> 3) & access != access):
            raise ValueError('账号 sender 需要只读访问 Claude 托管策略')
    return info


def _verify_marketplace(marketplace: Path) -> None:
    # 只读挂载限制账号容器写入。节点上的原始插件也必须由管理员独占修改。
    directories = [marketplace]
    while directories:
        for item in directories.pop().iterdir():
            if S_ISDIR(_trusted(item, sender_readable=True).st_mode):
                directories.append(item)


def shipped_direct_policy(data: Path, *, account_id: int, environment_id: str) -> dict:
    """准备同批正式发行的节点默认托管策略。

    :param data: 节点管理员持有的数据根。
    :param account_id: 当前权威 OAuth 账号。
    :param environment_id: 当前固定环境。
    :return: 只授予该账号、环境的受管配置。
    """
    _trusted(data, directory=True)
    plugin = 'flower2api-v2-direct'
    market = 'flower2api-release'
    qualified = f'{plugin}@{market}'
    settings = {
        'extraKnownMarketplaces': {market: {'source': {'source': 'directory', 'path': MANAGED_MARKETPLACE_PATH}}},
        'enabledPlugins': {qualified: True}, 'prependPlugins': ['sec-default@builtin'],
        'appendPlugins': [qualified],
    }
    catalog = {'name': market, 'owner': {'name': 'Flower2API'}, 'plugins': [{'name': plugin, 'source': f'./{plugin}'}]}

    def encode(value):
        return json.dumps(value, ensure_ascii=False, sort_keys=True).encode()

    files = {'managed-settings.json': encode(settings), 'marketplace/.claude-plugin/marketplace.json': encode(catalog)}
    mod_root = f'marketplace/{plugin}'
    for relative in ('.claude-plugin/plugin.json', 'hooks/hooks.json', 'hooks/engine.js'):
        source = DEFAULT_MOD / relative
        _trusted(source, directory=False)
        files[f'{mod_root}/{relative}'] = safe_read(source)
    key = sha256(encode({name: sha256(content).hexdigest() for name, content in files.items()})).hexdigest()
    root = data / DEFAULT_POLICY_DIRECTORY
    root.mkdir(mode=0o755, exist_ok=True)
    # 发布总目录只供编排访问。sender 分别挂载受管设置文件及目录市场。
    _trusted(root, directory=True)
    bundle = root / key
    # 新版本的不同内容发布到新目录。已运行 sender 的只读绑定继续持有自己的文件。
    if not bundle.exists():
        fd = directory_fd(root)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            if not bundle.exists():
                with TemporaryDirectory(prefix='.publish-', dir=root) as temporary:
                    stage = Path(temporary)
                    for name, content in files.items():
                        target = stage / name
                        atomic_text(target, content.decode('utf-8'), 0o444)
                    # 节点服务以 umask 077 运行。在发布前固定 Docker 会挂入 sender 的目录权限。
                    for directory, _, _ in os.walk(stage, topdown=False):
                        Path(directory).chmod(0o755)
                    stage.rename(bundle)
                    os.fsync(fd)
        finally:
            os.close(fd)
    _trusted(bundle, directory=True, sender_readable=True)
    market_path = bundle / 'marketplace'
    _trusted(market_path, directory=True, sender_readable=True)
    _verify_marketplace(market_path)
    for name, content in files.items():
        published = bundle / name
        _trusted(published, directory=False, sender_readable=True)
        if safe_read(published) != content:
            raise ValueError('节点发行托管策略与正式制品不符')
    return {'account_id': account_id, 'environment_id': environment_id, 'plugin': qualified, 'managed_order': True,
            'direct_hook_sha256': sha256(files[f'{mod_root}/hooks/engine.js']).hexdigest(),
            'settings_sha256': sha256(files['managed-settings.json']).hexdigest(),
            'marketplace_sha256': sha256(files['marketplace/.claude-plugin/marketplace.json']).hexdigest(),
            'release_bundle': key}


def managed_policy(data: Path, *, account_id: int | None, environment_id: str) -> dict | None:
    """核对管理员目录市场的来源和原账号绑定。

    @param data 节点私有数据根。
    @param account_id 网关登记的 OAuth 账号 ID。
    @param environment_id 账号运行环境 ID。
    @return 当前托管策略标识，未登记时为空。
    """
    if not re.fullmatch(r'[a-f0-9]{32}', environment_id):
        return None
    policies = data / POLICY_DIRECTORY
    bundle = policies / environment_id
    try:
        _trusted(bundle, directory=True)
    except (FileNotFoundError, NotADirectoryError):
        return None
    try:
        _trusted(data, directory=True)
        _trusted(policies, directory=True)
        binding = bundle / 'binding.json'
        _trusted(binding, directory=False)
        declared = strict_json(safe_read(binding))
        if (type(account_id) is not int or account_id <= 0 or type(declared.get('account_id')) is not int
                or declared['account_id'] != account_id or declared.get('environment_id') != environment_id):
            raise ValueError('Claude 托管策略与当前账号环境的绑定不符')
        plugin_id = declared.get('plugin')
        if not isinstance(plugin_id, str) or not re.fullmatch(r'[\w-]+@[\w-]+', plugin_id, re.ASCII):
            raise ValueError('Claude 托管策略缺少插件名和目录市场名')
        name, market = plugin_id.split('@')
        settings_file = bundle / 'managed-settings.json'
        settings_stat = _trusted(settings_file, directory=False, sender_readable=True)
        settings_bytes = safe_read(settings_file)
        settings = strict_json(settings_bytes)
        source = settings['extraKnownMarketplaces'][market]['source']
        if (settings['enabledPlugins'].get(plugin_id) is not True or source['source'] != 'directory'
                or source['path'] != MANAGED_MARKETPLACE_PATH):
            raise ValueError('Claude 管理设置须启用已绑定的本地目录市场插件')
        marketplace = bundle / 'marketplace'
        market_stat = _trusted(marketplace, directory=True, sender_readable=True)
        _verify_marketplace(marketplace)
        catalog = marketplace / '.claude-plugin' / 'marketplace.json'
        catalog_bytes = safe_read(catalog)
        entries = strict_json(catalog_bytes)
        candidates = [entry['source'] for entry in entries['plugins'] if entry['name'] == name]
        if entries['name'] != market or len(candidates) != 1 or not isinstance(candidates[0], str) or not candidates[0]:
            raise ValueError('Claude 目录市场须以唯一相对路径登记已绑定插件')
        relative = Path(candidates[0])
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Claude 托管插件必须位于管理员目录市场中')
        manifest = marketplace / relative / '.claude-plugin' / 'plugin.json'
        if strict_json(safe_read(manifest)).get('name') != name:
            raise ValueError('Claude 托管插件声明与目录市场不符')
        prepend = settings.get('prependPlugins', ['sec-default@builtin'])
        append_plugins = settings.get('appendPlugins', [])
        # 最后的受管钩子核验内层请求。其它 Mod 的改写与重试也须经过同一许可。
        ordered = (isinstance(prepend, list) and isinstance(append_plugins, list)
                   and append_plugins[-1:] == [plugin_id] and plugin_id not in prepend
                   and 'sec-default@builtin' in prepend
                   and settings['enabledPlugins'].get('sec-default@builtin') is not False)
        hook = marketplace / relative / 'hooks' / 'engine.js'
        hook_manifest = hook.with_name('hooks.json')
        hook_sha256 = None
        if hook.is_file() and hook_manifest.is_file() and strict_json(safe_read(hook_manifest)).get('modules') == ['./engine.js']:
            hook_sha256 = sha256(safe_read(hook)).hexdigest()
        # 目录市场按新目录发布。Docker 的文件和目录 bind 在旧容器中继续持有原 inode。
        return {'account_id': account_id, 'environment_id': environment_id, 'plugin': plugin_id, 'managed_order': ordered,
                'direct_hook_sha256': hook_sha256,
                'settings_sha256': sha256(settings_bytes).hexdigest(), 'marketplace_sha256': sha256(catalog_bytes).hexdigest(),
                'source_inodes': [[info.st_dev, info.st_ino] for info in (settings_stat, market_stat)]}
    except (AttributeError, KeyError, OSError, TypeError) as error:
        raise ValueError('Claude 托管策略的绑定、设置或市场清单不完整') from error
