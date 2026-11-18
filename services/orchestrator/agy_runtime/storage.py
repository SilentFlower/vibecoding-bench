"""独立包的固定执行体解码、私有状态与磁盘输出游标。"""
import hashlib
import json
import lzma
import math
import os
import re
from pathlib import Path
import stat
import sys
import threading
import tempfile
import uuid

ROOT=Path(__file__).parent
SOURCE_SHA='39816d49d5ab92229952987225c23ea3fed7580699dcb4a444e0388e0ac1ce43'
SOURCE_BYTES=265700040


def digest(path):
    """流式核验完整文件。@param path 文件。@return SHA256。"""
    result=hashlib.sha256()
    with Path(path).open('rb') as source:
        for data in iter(lambda:source.read(1048576),b''):result.update(data)
    return result.hexdigest()


def private_dir(path):
    """建立本用户的私有状态目录。@param path 路径。@return 绝对目录。"""
    path=Path(path).absolute()
    if path.is_symlink():raise ValueError('状态目录必须为普通目录')
    path.mkdir(parents=True,exist_ok=True,mode=0o700)
    info=path.stat()
    if info.st_uid!=os.getuid() or info.st_mode&0o077:raise ValueError('状态目录需要当前用户所有且权限0700')
    return path


def verify_resources():
    """核验随包资源身份。@return 无返回值。"""
    admission=json.loads((ROOT/'resources/admission.json').read_text())
    if admission['source_sha256']!=SOURCE_SHA:raise ValueError('资源版本不匹配')
    for relative,expected in admission['resource_hashes'].items():
        if digest(ROOT/relative)!=expected:raise ValueError('包内资源身份不匹配')


def binary(state, source):
    """核验固定原版路径并返回执行入口。@param state 当前私有状态。@param source 固定镜像内原版。@return 已核验执行路径。"""
    from .image_pool import receive
    verify_resources()
    if os.environ.get('AGY_RUNTIME_IMAGE_SOCKET'):
        descriptor, metadata = receive(os.environ['AGY_RUNTIME_IMAGE_SOCKET'])
        return Path('/proc/' + str(os.getpid()) + '/fd/' + str(descriptor))
    path = Path(source)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_size != SOURCE_BYTES or info.st_mode & 0o022 or digest(path) != SOURCE_SHA:
        raise ValueError('AGY固定执行体身份无效')
    return path


def config(path):
    """读取受管理端发布的私有OAuth启动配置。@param path 私有配置。@return 已核验的冻结配置。"""
    from .credentials import read_private, read_access_document
    value = read_private(Path(path))
    allowed = {'home','public_model','native_model','binary_path','proxy_url','rotate_after',
        'startup_timeout','retire_timeout','cancel_timeout','runtime_env','capture_enabled','capture_root','account_id','credential_generation'}
    if set(value) - allowed:
        raise ValueError('AGY启动配置字段无效')
    for name in ['home','public_model','binary_path']:
        if not isinstance(value.get(name),str) or not value[name]:
            raise ValueError('AGY启动配置缺少必要字段')
    for name in ['account_id','credential_generation']:
        if type(value.get(name)) is not int or value[name]<1:
            raise ValueError('AGY启动归属无效')
    value['home'] = private_dir(value['home'])
    read_access_document(value['home'])
    proxy = value.get('proxy_url','')
    if not isinstance(proxy,str) or any(ord(c)<32 for c in proxy):
        raise ValueError('AGY代理配置无效')
    value['proxy_url'] = proxy
    for key, default in [('startup_timeout',90),('retire_timeout',60),('cancel_timeout',10)]:
        item = value.get(key,default)
        if type(item) not in [int,float] or not math.isfinite(item) or not 0<item<=86400:
            raise ValueError('AGY生命周期预算无效')
        value[key] = item
    rotate = value.get('rotate_after')
    if rotate is not None and (type(rotate) is not int or rotate<1):
        raise ValueError('AGY轮换次数无效')
    value['rotate_after'] = rotate
    env = value.get('runtime_env',{})
    if not isinstance(env,dict) or set(env)-{'GOGC','GOMEMLIMIT','GOMAXPROCS'} or any(not isinstance(v,str) or not re.fullmatch(r'(?:off|[0-9]+(?:B|KiB|MiB|GiB|TiB)?)',v) for v in env.values()):
        raise ValueError('AGY运行资源参数无效')
    value['runtime_env'] = env
    if type(value.get('capture_enabled',False)) is not bool:
        raise ValueError('AGY采集设置无效')
    value.setdefault('capture_enabled',False)
    if value.get('capture_root') is not None:
        value['capture_root']=str(private_dir(value['capture_root']))
    return value


class Output:
    """以有界私有暂存隔离客户端慢读，默认结束后不保留业务正文。"""

    def __init__(self, path=None, pending_limit=67108864):
        """建立输出游标。@param path 显式采集文件，缺省使用匿名临时文件。@param pending_limit 未消费字节上限。@return 无。"""
        if path is not None and path.is_symlink():
            raise ValueError('AGY协议采集文件类型无效')
        self.archive = path is not None
        self.writer = path.open('w+b', buffering=0) if self.archive else tempfile.TemporaryFile('w+b', buffering=0)
        self.condition = threading.Condition()
        self.written = 0
        self.read = 0
        self.finished = False
        self.error = None
        self.pending_limit = pending_limit
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def emit(self, event):
        """交付完整版本化事件。@param event 私有协议对象。@return 无。"""
        raw = (json.dumps(event, ensure_ascii=False, separators=(',', ':')) + '\n').encode()
        with self.condition:
            if self.error or self.finished:
                raise RuntimeError('AGY输出通道已关闭')
            if self.written - self.read + len(raw) > self.pending_limit:
                raise RuntimeError('AGY输出消费积压超限')
            # 已消费窗口可以回收，避免持续复用worker时临时文件无限增长。
            if not self.archive and self.written == self.read:
                self.writer.truncate(0)
                self.writer.seek(0)
                self.written = self.read = 0
            if self.writer.write(raw) != len(raw):
                raise OSError('AGY协议暂存写入不完整')
            self.written += len(raw)
            self.condition.notify_all()

    def run(self):
        """由唯一线程按游标写stdout，避免并发事件相互穿插。@return 无。"""
        try:
            while True:
                with self.condition:
                    while self.read == self.written and not self.finished:
                        self.condition.wait(.1)
                    if self.read == self.written and self.finished:
                        return
                    raw = os.pread(self.writer.fileno(), min(65536, self.written - self.read), self.read)
                if not raw:
                    raise OSError('AGY输出暂存游标无效')
                sys.stdout.buffer.write(raw)
                sys.stdout.buffer.flush()
                with self.condition:
                    self.read += len(raw)
                    self.condition.notify_all()
        except Exception as error:
            self.error = type(error).__name__

    def close(self):
        """结束交付并释放临时文件。@return 无。"""
        with self.condition:
            self.finished = True
            self.condition.notify_all()
        self.thread.join(timeout=15)
        if not self.thread.is_alive():
            self.writer.close()
