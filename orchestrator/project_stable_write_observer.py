"""验证稳定原子输出和软链接拒绝，不限定合理文件错误的唯一异常类型。"""
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory


def main() -> None:
    """核对真实文件字节、模式、不变时状态和链接拒绝的无副作用。:return: None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    sys.path.insert(0, str(root / 'library/src'))
    import click
    checks = dict.fromkeys(('stable_write_content', 'stable_write_unchanged', 'stable_write_symlink'), False)
    try:
        from click.writing import write_if_changed
        with TemporaryDirectory() as temporary:
            folder = Path(temporary)
            path = folder / 'out'
            path.write_bytes(b'old\r\n')
            path.chmod(0o644)
            changed = write_if_changed(path, b'new\r\n')
            checks['stable_write_content'] = (bool(changed) and path.read_bytes() == b'new\r\n'
                and path.stat().st_mode & 0o777 == 0o644)
            before = path.stat()
            unchanged = write_if_changed(path, b'new\r\n')
            after = path.stat()
            checks['stable_write_unchanged'] = (not unchanged
                and (before.st_ino, before.st_mtime_ns, before.st_mode) == (after.st_ino, after.st_mtime_ns, after.st_mode))
            link = folder / 'link'
            link.symlink_to(path)
            try:
                write_if_changed(link, b'bad')
            except (ValueError, OSError):
                # 拒绝可以表示为参数错误或文件错误，但不能写穿链接或遗留临时文件。
                checks['stable_write_symlink'] = (link.is_symlink() and path.read_bytes() == b'new\r\n'
                    and path.stat().st_mode & 0o777 == 0o644
                    and {item.name for item in folder.iterdir()} == {'out', 'link'})
    except Exception:
        pass
    codes = [name for name, passed in checks.items() if not passed]
    print(json.dumps({'candidate_import': Path(click.__file__).resolve().is_relative_to(root / 'library'),
        'business': not codes, 'feedback_codes': codes}))


if __name__ == '__main__':
    main()
