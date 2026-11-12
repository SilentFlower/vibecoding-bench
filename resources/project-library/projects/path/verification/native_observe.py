"""在独立临时目录观察真实文件字节、遍历、合并与取消恢复。"""
from __future__ import annotations

import json
import os
from pathlib import Path as StdPath
import shutil
import stat
import sys
from tempfile import TemporaryDirectory

import path
from path import Path


class RewriteCancelled(BaseException):
    """模拟应用自定义的非Exception取消信号，只在当前临时文件用户块抛出。"""


def formats() -> dict:
    """核文本换行转换与二进制保真。@return 实际文件字节事实。"""
    with TemporaryDirectory(prefix='path-formats-') as directory:
        root = Path(directory)
        value = '茶\r\nB\rC\n'
        normal, unchanged, explicit = (root / name for name in ('normal', 'unchanged', 'explicit'))
        normal.write_text(value, encoding='utf-8')
        unchanged.write_text(value, encoding='utf-8', linesep=None)
        explicit.write_text(value, encoding='utf-8', linesep='\r\n')
        binary = b'\x00\xff\r\n\x80\r\x00'
        source, copied = root / 'input.bin', root / 'output.bin'
        source.write_bytes(binary)
        with copied.open('wb') as output:
            for chunk in source.chunks(2, mode='rb'):
                output.write(chunk)
        return {'write_text_line_policy_is_explicit': normal.bytes() == '茶\nB\nC\n'.encode()
                and unchanged.bytes() == value.encode() and explicit.bytes() == '茶\r\nB\r\nC\r\n'.encode(),
            'binary_chunks_preserve_exact_bytes': copied.bytes() == binary}


def traversal() -> dict:
    """核非递归glob、递归盘点和显式子树剪枝。@return 遍历事实。"""
    with TemporaryDirectory(prefix='path-traversal-') as directory:
        root = Path(directory)
        for relative in ('a.txt', 'level/b.txt', 'level/deep/c.txt', 'skip/secret.txt'):
            target = StdPath(directory) / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(relative, encoding='utf-8')
        globbed = sorted(str(StdPath(str(item)).relative_to(directory)) for item in root.glob('**/*.txt'))
        walked = sorted(str(StdPath(str(item)).relative_to(directory)) for item in root.walkfiles('*.txt'))
        generator = root.walk()
        seen = []
        try:
            item = next(generator)
            while True:
                seen.append(str(StdPath(str(item)).relative_to(directory)))
                # send返回下一个实际元素，必须继续消费该返回值，不能用普通for循环悄悄丢项。
                item = generator.send((lambda: False) if item.name == 'skip' else None)
        except StopIteration:
            pass
        finally:
            generator.close()
        return {'glob_double_star_is_not_recursive': globbed == ['level/b.txt', 'skip/secret.txt']
                and walked == ['a.txt', 'level/b.txt', 'level/deep/c.txt', 'skip/secret.txt'],
            'walk_send_can_prune_one_subtree': 'skip' in seen and 'skip/secret.txt' not in seen
                and {'a.txt', 'level/b.txt', 'level/deep/c.txt'}.issubset(seen)}


def merging() -> dict:
    """观察合并、忽略与自定义复制回调，不对真实目录做同步。@return 合并事实。"""
    with TemporaryDirectory(prefix='path-merging-') as directory:
        source, target = (Path(directory) / name for name in ('source', 'target'))
        source.makedirs_p()
        target.makedirs_p()
        (source / 'same.txt').write_bytes(b'new')
        (source / 'ignored.tmp').write_bytes(b'temporary')
        (source / 'nested').makedirs_p()
        (source / 'nested/keep.txt').write_bytes(b'nested')
        (target / 'same.txt').write_bytes(b'old')
        (target / 'target-only.txt').write_bytes(b'retain')
        copied = []

        def copy_file(original, destination):
            """保留实际复制语义并记录回调。@param original 源。@param destination 目标。@return 实际复制返回值。"""
            copied.append(StdPath(str(original)).name)
            return shutil.copy2(original, destination)

        source.merge_tree(target, ignore=shutil.ignore_patterns('*.tmp'), copy_function=copy_file)
        return {'merge_overwrites_and_retains_target_only': (target / 'same.txt').bytes() == b'new'
                and (target / 'target-only.txt').bytes() == b'retain',
            'existing_ignore_and_copy_function_are_used': not (target / 'ignored.tmp').exists()
                and (target / 'nested/keep.txt').bytes() == b'nested' and sorted(copied) == ['keep.txt', 'same.txt']}


def recovery(engineering: bool) -> dict:
    """只在合成用户块抛取消，保留异常对象、原字节和流关闭事实。

    :param engineering: 是否验证明确授权的全部取消异常目标。
    :return: 真实恢复与既有行为，不将控制异常传播到测试进程外。
    """
    with TemporaryDirectory(prefix='path-recovery-') as directory:
        root = Path(directory)
        records = []
        failures = [RuntimeError] if not engineering else [KeyboardInterrupt, SystemExit, GeneratorExit, RewriteCancelled]
        for index, exception_type in enumerate(failures):
            document = root / ('case-' + str(index))
            original = b'original\r\n\x00\xff'
            document.write_bytes(original)
            document.chmod(0o640)
            exception = exception_type('synthetic interruption')
            extension = '.retained' if index % 2 else None
            options = {'mode': 'rb', 'backup_extension': extension}
            caught, reader, writer = None, None, None
            try:
                with document.in_place(**options) as (reader, writer):
                    assert reader.read() == original
                    writer.write(b'partial')
                    raise exception
            except BaseException as error:
                caught = error
            backup = Path(str(document) + (extension or '.bak'))
            records.append({'restored': document.bytes() == original, 'propagated': caught is exception,
                'closed': reader.closed and writer.closed, 'backup_removed': not backup.exists(),
                'mode_preserved': stat.S_IMODE(os.stat(document).st_mode) == 0o640})
            # 原版失败路径没有关闭流，取证后仍需释放本脚本实际创建的描述符。
            if not reader.closed:
                reader.close()
            if not writer.closed:
                writer.close()
        normal = root / 'normal'
        normal.write_bytes(b'old')
        with normal.in_place(mode='rb') as (reader, writer):
            writer.write(b'new')
        facts = {'normal_success_and_backup_cleanup': normal.bytes() == b'new' and reader.closed and writer.closed
            and not Path(str(normal) + '.bak').exists()}
        if engineering:
            facts.update(all_user_block_interruptions_restore_bytes=all(row['restored'] for row in records),
                same_exception_objects_propagate=all(row['propagated'] for row in records),
                interrupted_streams_close=all(row['closed'] for row in records),
                backup_and_permissions_preserved=all(row['backup_removed'] and row['mode_preserved'] for row in records))
        else:
            facts['ordinary_runtime_error_restores_bytes'] = all(all(row.values()) for row in records)
        return facts


def main() -> None:
    """输出当前任务明确冻结的真实事实。@return None。"""
    task = sys.argv[1]
    fields = {'PA-U01': ('write_text_line_policy_is_explicit',),
        'PA-C01': ('binary_chunks_preserve_exact_bytes',),
        'PA-U02': ('glob_double_star_is_not_recursive',),
        'PA-C02': ('walk_send_can_prune_one_subtree',),
        'PA-U03': ('merge_overwrites_and_retains_target_only',),
        'PA-C03': ('existing_ignore_and_copy_function_are_used',),
        'PA-P01': ('normal_success_and_backup_cleanup', 'ordinary_runtime_error_restores_bytes'),
        'PA-M01': ('all_user_block_interruptions_restore_bytes', 'same_exception_objects_propagate',
            'interrupted_streams_close', 'backup_and_permissions_preserved', 'normal_success_and_backup_cleanup')}
    if task in ('PA-U01', 'PA-C01'):
        facts = formats()
    elif task in ('PA-U02', 'PA-C02'):
        facts = traversal()
    elif task in ('PA-U03', 'PA-C03'):
        facts = merging()
    else:
        facts = recovery(task == 'PA-M01')
    root = StdPath(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    print(json.dumps({'candidate_import': StdPath(path.__file__).resolve() == root / 'library/path/__init__.py',
        **{field: facts[field] for field in fields[task]}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
