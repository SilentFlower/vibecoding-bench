"""迁移清单的磁盘索引和兼容原JSON格式的逐条读写。"""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping

from cluster_archive_schema import SCHEMA


def _unique(pairs):
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError('迁移清单包含重复字段')
    return result


class _JsonStream:
    """按单条文件元数据读取JSON，整份清单留在磁盘。"""

    def __init__(self, source) -> None:
        """保存文本流及逐条解码器。:param source: 原文本流。:return: None。"""
        self.source, self.buffer, self.eof = source, '', False
        self.decoder = json.JSONDecoder(object_pairs_hook=_unique, parse_constant=self._invalid)

    def _invalid(self, value):
        raise ValueError('迁移清单包含非法数值')

    def _fill(self) -> None:
        chunk = self.source.read(16384)
        if not chunk:
            self.eof = True
        self.buffer += chunk

    def peek(self) -> str:
        """读取下一个非空白字符。:return: 字符或EOF空串。"""
        while True:
            self.buffer = self.buffer.lstrip()
            if self.buffer or self.eof:
                return self.buffer[:1]
            self._fill()

    def take(self, expected: str) -> None:
        """核对JSON结构字符。:param expected: 预期字符。:return: None。"""
        if self.peek() != expected:
            raise ValueError('迁移清单结构无效')
        self.buffer = self.buffer[1:]

    def value(self):
        """读取一个文件元数据值。:return: 已解码值。"""
        self.peek()
        while True:
            try:
                value, end = self.decoder.raw_decode(self.buffer)
                self.buffer = self.buffer[end:]
                return value
            except json.JSONDecodeError:
                # 此预算只约束单条路径/权限/摘要元数据，整份清单和文件内容均流式读取。
                if self.eof or len(self.buffer) > 128 * 1024:
                    raise ValueError('迁移单条文件元数据格式无效') from None
                self._fill()

    def pairs(self):
        """遍历JSON对象键，调用方逐个消费值。:return: 键迭代器。"""
        self.take('{')
        if self.peek() != '}':
            while True:
                key = self.value()
                if not isinstance(key, str):
                    raise ValueError('迁移清单字段必须为字符串')
                self.take(':')
                yield key
                if self.peek() != ',':
                    break
                self.take(',')
        self.take('}')


class ArchiveIndex(Mapping):
    """私有临时SQLite清单，保留原映射访问并限制页缓存。

    :param path: 当前操作临时目录中的新索引文件。
    """

    def __init__(self, path) -> None:
        """在本操作临时目录建立清单。:param path: 新索引路径。:return: None。"""
        self.connection = sqlite3.connect(path)
        self.connection.execute('PRAGMA cache_size=-2048')
        self.connection.execute('PRAGMA temp_store=FILE')
        self.connection.execute(SCHEMA)
        self.count = 0

    def __len__(self):
        """返回实际条目数。:return: 数量。"""
        return self.count

    def __iter__(self):
        """逐条读取路径。:return: 路径迭代器。"""
        return (row[0] for row in self.connection.execute('SELECT path FROM entries ORDER BY path'))

    def __getitem__(self, name):
        """读取单条元数据。:param name: 原路径。:return: 元数据。"""
        row = self.connection.execute('SELECT item FROM entries WHERE path=?', (name,)).fetchone()
        if row is None:
            raise KeyError(name)
        return json.loads(row[0])

    def add(self, name, item) -> None:
        """保存唯一条目，拒绝重复路径。:param name: 路径。:param item: 元数据。:return: None。"""
        if not isinstance(name, str):
            raise ValueError('迁移路径类型无效')
        try:
            self.connection.execute('INSERT INTO entries(path,item,depth) VALUES(?,?,?)',
                (name, json.dumps(item, ensure_ascii=True, separators=(',', ':'), allow_nan=False), name.count('/')))
        except sqlite3.IntegrityError:
            raise ValueError('迁移清单包含重复路径') from None
        self.count += 1

    def items(self):
        """按原字典排序语义逐条读取。:return: 路径与元数据。"""
        for name, raw in self.connection.execute('SELECT path,item FROM entries ORDER BY path'):
            yield name, json.loads(raw)

    def ordered(self, *, reverse=False):
        """按目录深度读取，排序在磁盘完成。:param reverse: 子目录优先。:return: 条目。"""
        order = 'DESC' if reverse else 'ASC'
        for name, raw in self.connection.execute('SELECT path,item FROM entries ORDER BY depth ' + order + ',path'):
            yield name, json.loads(raw)

    def mark(self, name) -> None:
        """登记一次实际出现，避免全量seen集合。:param name: 路径。:return: None。"""
        if self.connection.execute('UPDATE entries SET seen=1 WHERE path=? AND seen=0', (name,)).rowcount != 1:
            raise ValueError('迁移包包含重复或未登记的文件')

    def complete(self, *, root=False) -> bool:
        """核对全部条目已消费。:param root: 是否包括根。:return: 已完整消费。"""
        sql = 'SELECT 1 FROM entries WHERE seen=0' + ('' if root else " AND path!='.'") + ' LIMIT 1'
        return self.connection.execute(sql).fetchone() is None

    def compare(self, entries) -> bool:
        """逐条对比实际树，检测新增、修改及缺失。:param entries: 实际盘点。:return: 一致。"""
        self.connection.execute('UPDATE entries SET seen=0')
        for name, item in entries:
            if self.get(name) != item:
                return False
            self.mark(name)
        return self.complete(root=True)

    def write(self, output, identity: dict, excluded: dict) -> int:
        """流式写原格式清单。:param output: 二进制私有文件。:param identity: 身份。:param excluded: 排除依据。:return: 字节数。"""
        output.write(b'{"identity":' + json.dumps(identity, separators=(',', ':')).encode() + b',"entries":{')
        first = True
        for name, item in self.items():
            if not first:
                output.write(b',')
            first = False
            output.write(json.dumps(name, ensure_ascii=True).encode() + b':' +
                json.dumps(item, ensure_ascii=True, separators=(',', ':')).encode())
        output.write(b'},"excluded":' + json.dumps(excluded, ensure_ascii=True, separators=(',', ':')).encode() + b'}')
        return output.tell()

    def load(self, source) -> dict:
        """流式读取历史及新清单。:param source: UTF-8文本流。:return: 身份和排除项。"""
        reader, document = _JsonStream(source), {}
        for key in reader.pairs():
            if key in document or key not in ('identity', 'entries', 'excluded'):
                raise ValueError('迁移清单字段重复或无效')
            if key == 'entries':
                document[key] = self
                for name in reader.pairs():
                    self.add(name, reader.value())
            else:
                document[key] = reader.value()
        if reader.peek() or set(document) != {'identity', 'entries', 'excluded'}:
            raise ValueError('迁移清单结构无效')
        return document

    def close(self) -> None:
        """释放磁盘索引。:return: None。"""
        self.connection.close()
