"""从固定包内归档一次解码封存映像，并通过受控Unix连接交接只读FD。"""
from .validation import require
import array
import fcntl
import hashlib
import json
import lzma
import os
from pathlib import Path
import socket
import stat
import struct
import threading

SOURCE_SHA = '39816d49d5ab92229952987225c23ea3fed7580699dcb4a444e0388e0ac1ce43'
SOURCE_BYTES = 265700040
SEALS = fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL


def identity(fd):
    """读取映像的真实FD身份。@param fd 句柄。@return 元数据。"""
    value = os.fstat(fd)
    return {'dev': value.st_dev, 'ino': value.st_ino, 'bytes': value.st_size, 'uid': value.st_uid, 'gid': value.st_gid, 'mode': stat.S_IMODE(value.st_mode), 'nlink': value.st_nlink, 'seals': fcntl.fcntl(fd, fcntl.F_GET_SEALS), 'access': fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE}


class ImagePool:
    """只发布完整核验后的封存映像，解码失败保持明确失败状态。"""

    def __init__(self, archive):
        """创建惰性池。@param archive 受控包内归档。@return 无。"""
        self.archive = Path(archive)
        self.lock = threading.Lock()
        self.fd = None
        self.failure = None
        self.closed = False
        self.decode_calls = 0
        self.acquires = 0
        self.decoded_bytes = 0

    def acquire(self):
        """并发取得独立只读文件描述。@return 归调用方关闭的FD。"""
        with self.lock:
            if self.closed:
                raise ValueError('image_pool_closed')
            if self.failure:
                raise ValueError(self.failure)
            if self.fd is None:
                self.decode_calls += 1
                writable = os.memfd_create('agy-native-runtime', os.MFD_ALLOW_SEALING | os.MFD_CLOEXEC)
                try:
                    digest = hashlib.sha256()
                    count = 0
                    with (lzma.open(self.archive, 'rb') if self.archive.suffix == '.xz' else self.archive.open('rb')) as stream:
                        while block := stream.read(1048576):
                            count += len(block)
                            if count > SOURCE_BYTES:
                                raise ValueError('image_decoded_size')
                            digest.update(block)
                            view = memoryview(block)
                            while view:
                                view = view[os.write(writable, view):]
                    if count != SOURCE_BYTES or digest.hexdigest() != SOURCE_SHA:
                        raise ValueError('image_decoded_identity')
                    os.fchmod(writable, 0o555)
                    fcntl.fcntl(writable, fcntl.F_ADD_SEALS, SEALS)
                    readonly = os.open('/proc/self/fd/' + str(writable), os.O_RDONLY | os.O_CLOEXEC)
                    require(identity(readonly)['seals'] == SEALS)
                    self.fd = readonly
                    self.decoded_bytes = count
                except Exception as error:
                    self.failure = str(error) if isinstance(error, ValueError) else 'image_decode_failed'
                    raise ValueError(self.failure) from error
                finally:
                    os.close(writable)
            self.acquires += 1
            return os.open('/proc/self/fd/' + str(self.fd), os.O_RDONLY | os.O_CLOEXEC)

    def close(self):
        """停止准入并释放池引用。@return 无。"""
        with self.lock:
            self.closed = True
            if self.fd is not None:
                os.close(self.fd)
                self.fd = None


class Broker:
    """按Unix peer UID准入并交付固定版本的只读映像FD。"""

    def __init__(self, path, pool, allowed_uids):
        """监听受控本地端点。@param path Socket路径。@param pool 映像池。@param allowed_uids 准入UID集合。@return 无。"""
        self.path = Path(path)
        self.pool = pool
        self.allowed_uids = set(allowed_uids)
        self.records = []
        self.stop = threading.Event()
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        self.socket.bind(str(path))
        os.chmod(path, 0o600)
        self.socket.listen(32)
        self.socket.settimeout(.2)
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        """接收连接并由独立线程完成共享初始化等待。@return 无。"""
        while not self.stop.is_set():
            try:
                connection, _ = self.socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self.handle, args=(connection,), daemon=True).start()

    def handle(self, connection):
        """核验真实peer并交付一次FD。@param connection 本地连接。@return 无。"""
        record = {}
        fd = None
        try:
            pid, uid, gid = struct.unpack('3i', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3i')))
            record.update(pid=pid, uid=uid, gid=gid)
            connection.settimeout(5)
            data = connection.recv(4097)
            if uid not in self.allowed_uids:
                raise ValueError('image_peer_not_allowed')
            request = json.loads(data)
            if len(data) > 4096 or not isinstance(request, dict) or type(request.get('schema_version')) is not int or request != {'schema_version': 1, 'type': 'image', 'source_sha256': SOURCE_SHA}:
                raise ValueError('image_request_invalid')
            fd = self.pool.acquire()
            metadata = {'schema_version': 1, 'source_sha256': SOURCE_SHA, **identity(fd)}
            connection.sendmsg([json.dumps(metadata).encode()], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array('i', [fd]))])
            record.update(delivered=True, identity=metadata)
        except Exception as error:
            record.update(delivered=False, error=str(error))
            try:
                connection.send(json.dumps({'error': str(error)}).encode())
            except OSError:
                pass
        finally:
            if fd is not None:
                os.close(fd)
            self.records.append(record)
            connection.close()

    def close(self):
        """关闭端点，等待接收线程结束。@return 无。"""
        self.stop.set()
        self.socket.close()
        self.thread.join(2)
        self.path.unlink(missing_ok=True)


def receive(path):
    """取得broker交接的封存只读FD。@param path 受控Socket。@return FD及已核验元数据。"""
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    connection.settimeout(30)
    fds = []
    try:
        connection.connect(str(path))
        connection.send(json.dumps({'schema_version': 1, 'type': 'image', 'source_sha256': SOURCE_SHA}).encode())
        data, ancillary, flags, _ = connection.recvmsg(4096, socket.CMSG_SPACE(4 * 4), socket.MSG_CMSG_CLOEXEC)
        for level, kind, value in ancillary:
            if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
                values = array.array('i')
                values.frombytes(value[:len(value) - len(value) % values.itemsize])
                fds.extend(values)
        metadata = json.loads(data)
        if metadata.get('error'):
            raise ValueError(metadata['error'])
        if flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC) or len(fds) != 1:
            raise ValueError('image_fd_shape')
        actual = identity(fds[0])
        if actual != {key: metadata[key] for key in actual} or metadata['schema_version'] != 1 or metadata['source_sha256'] != SOURCE_SHA:
            raise ValueError('image_fd_metadata')
        if (actual['bytes'] != SOURCE_BYTES or actual['uid'] != os.getuid() or actual['gid'] != os.getgid() or actual['mode'] != 0o555 or actual['nlink'] != 0 or actual['seals'] != SEALS or actual['access'] != os.O_RDONLY):
            raise ValueError('image_fd_identity')
        return fds.pop(), metadata
    finally:
        connection.close()
        for fd in fds:
            os.close(fd)
