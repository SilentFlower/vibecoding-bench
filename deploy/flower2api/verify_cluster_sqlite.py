"""随机部署专用SQLite锁诊断，仅记录时序与调用位置。"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import threading
import time
import traceback
import weakref
from pathlib import Path


_connections=weakref.WeakSet()


def _frames(frame=None) -> list[str]:
    frames=traceback.extract_stack(frame,limit=9)
    return [f'{Path(item.filename).name}:{item.lineno}:{item.name}' for item in frames]


def _diagnostic(connection, event: str, elapsed: float) -> None:
    tracked=[]
    for current in list(_connections):
        tracked.append({'thread':current.trace_thread,'native_thread_id':current.trace_native,'phase':current.trace_phase,'verb':current.trace_verb,
            'transaction_age':time.monotonic()-current.trace_transaction if current.trace_transaction is not None else None,
            'phase_age':time.monotonic()-current.trace_since,'caller':current.trace_caller})
    frames=sys._current_frames()
    threads=[{'name':thread.name,'frames':_frames(frames[thread.ident])} for thread in threading.enumerate()
        if thread.ident in frames]
    locks=[]
    try:
        inode=str(Path(connection.trace_path).stat().st_ino)
        locks=[line for line in Path('/proc/locks').read_text().splitlines()
            if any(part.rsplit(':',1)[-1]==inode for part in line.split())]
    except OSError:
        pass
    print(json.dumps({'sqlite_event':event,'unix_time':time.time(),'native_thread_id':threading.get_native_id(),
        'elapsed':elapsed,'tracked':tracked,'threads':threads,'owned_inode_locks':locks},
        ensure_ascii=False),file=sys.stderr,flush=True)


class _TracedConnection(sqlite3.Connection):
    """保持原SQLite行为，错误和慢操作输出无SQL参数的诊断。"""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args,**kwargs)
        self.trace_path=args[0]
        self.trace_thread=threading.current_thread().name
        self.trace_native=threading.get_native_id()
        self.trace_phase='idle'
        self.trace_verb=''
        self.trace_transaction=None
        self.trace_since=time.monotonic()
        self.trace_caller=[]
        _connections.add(self)

    def execute(self, sql, parameters=()):
        """原样执行SQL，仅记录类别和调用位置。:param sql: 原语句。:param parameters: 原参数。:return: 原cursor。"""
        self.trace_thread=threading.current_thread().name
        self.trace_native=threading.get_native_id()
        self.trace_verb=sql.lstrip().split(None,1)[0].upper() if sql.strip() else ''
        self.trace_phase='execute'
        self.trace_since=time.monotonic()
        self.trace_caller=_frames()
        try:
            result=super().execute(sql,parameters)
        except sqlite3.OperationalError:
            _diagnostic(self,'execute-error',time.monotonic()-self.trace_since)
            raise
        else:
            if self.in_transaction:
                if self.trace_transaction is None:
                    self.trace_transaction=self.trace_since
            else:
                self.trace_transaction=None
            if time.monotonic()-self.trace_since>1:
                _diagnostic(self,'slow-execute',time.monotonic()-self.trace_since)
            return result
        finally:
            self.trace_phase='execute-returned'

    def __exit__(self, *args):
        self.trace_thread=threading.current_thread().name
        self.trace_native=threading.get_native_id()
        self.trace_phase='transaction-exit'
        self.trace_since=time.monotonic()
        self.trace_caller=_frames()
        try:
            return super().__exit__(*args)
        finally:
            if time.monotonic()-self.trace_since>1:
                _diagnostic(self,'slow-transaction-exit',time.monotonic()-self.trace_since)
            self.trace_phase='transaction-exited'
            if not self.in_transaction:
                self.trace_transaction=None

    def close(self) -> None:
        """关闭原连接并移除诊断引用。:return: None。"""
        try:
            super().close()
        finally:
            _connections.discard(self)


def traced_connect(path: Path) -> sqlite3.Connection:
    """为本次隔离中央数据库创建原行为的带诊断连接。

    :param path: 随机测试部署的central/bench.sqlite。
    :return: 原默认超时与连接模式的SQLite连接。
    """
    if (os.environ.get('CLUSTER_DOCKER_TEST')!='1' or os.environ.get('CLUSTER_TEST_SQLITE_TRACE')!='1'
            or path.name!='bench.sqlite' or path.parent.name!='central'):
        raise ValueError('SQLite诊断仅用于当前隔离集群夹具')
    return sqlite3.connect(path,factory=_TracedConnection)
