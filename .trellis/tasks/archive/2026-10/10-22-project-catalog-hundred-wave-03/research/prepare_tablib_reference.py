"""封存按键对齐修复、只排序值的错误候选和公开原版控制。"""
from pathlib import Path
from shutil import copyfile, copytree


def main() -> None:
    """仅写明确参考目录，原固定源码及测试保持完整。@return None。"""
    work = Path('.deploy/project-catalog-hundred/stage-03')
    seed = work / 'drafts/projects/tablib/seed'
    reference, wrong, original = work / 'references/tablib', work / 'wrong-candidates/tablib-sort-values', work / 'public-test-controls/tablib-original'
    for destination in (reference, wrong, original):
        copytree(seed, destination)
        copyfile(Path(__file__).with_name('tablib-public-tests.py'), destination / 'app/test_dict_import.py')
    relative = 'library/src/tablib/core.py'
    text = (seed / relative).read_text()
    old = '''        elif isinstance(pickle[0], dict):
            self.wipe()
            self.headers = list(pickle[0].keys())
            for row in pickle:
                self.append(Row(list(row.values())))'''
    if text.count(old) != 1:
        raise ValueError('固定字典导入块变化')
    repaired = '''        elif isinstance(pickle[0], dict):
            headers = list(pickle[0].keys())
            # 先核整个映射批次，避免错误输入先清空已有数据或留下部分新记录。
            if any(not isinstance(row, dict) or set(row) != set(headers) for row in pickle):
                raise UnsupportedFormat(error_details)
            rows = [[row[header] for header in headers] for row in pickle]
            self.wipe()
            self.headers = headers
            for row in rows:
                self.append(Row(row))'''
    (reference / relative).write_text(text.replace(old, repaired))
    incomplete = old.replace('list(row.values())', '[row[key] for key in sorted(row)]')
    (wrong / relative).write_text(text.replace(old, incomplete))
    print('已封存按键对齐参考、错误排序候选和八项公开测试原版控制。')


if __name__ == '__main__':
    main()
