"""从实际固定源码制作完整链接修复、漏属性反例和公开原版控制。"""
from pathlib import Path
from shutil import copyfile, copytree


def main() -> None:
    """仅写本阶段独立参考目录，保留原版源码。@return None。"""
    work = Path('.deploy/project-catalog-hundred/stage-03')
    seed = work / 'drafts/projects/feedgen/seed'
    reference, wrong, original = work / 'references/feedgen', work / 'wrong-candidates/feedgen-rel-only', work / 'public-test-controls/feedgen-original'
    for destination in (reference, wrong, original):
        copytree(seed, destination)
        copyfile(Path(__file__).with_name('feedgen-public-tests.py'), destination / 'app/test_atom_link.py')
    relative = 'library/feedgen/entry.py'
    text = (seed / relative).read_text()
    start = text.index('        for link in self.__atom_link or []:')
    end = text.index("        _add_text_elm(entry, self.__atom_summary, 'summary')", start)
    block = text[start:end]
    if block.count("link.get(") != 5 or block.count("link['") != 6:
        raise ValueError('固定序列化块已变化')
    repaired = block.replace('for link in ', 'for data in ').replace("href=link['href']", "href=data['href']")
    repaired = repaired.replace('link.get(', 'data.get(')
    for name in ('rel', 'type', 'hreflang', 'title', 'length'):
        repaired = repaired.replace("= link['" + name + "']", "= data['" + name + "']")
    (reference / relative).write_text(text[:start] + repaired + text[end:])
    incomplete = block.replace('for link in ', 'for data in ').replace("href=link['href']", "href=data['href']")
    incomplete = incomplete.replace("link.get('rel')", "data.get('rel')").replace("= link['rel']", "= data['rel']")
    (wrong / relative).write_text(text[:start] + incomplete + text[end:])
    print('已封存完整修复、只修rel的错误候选及三项公开测试原版控制。')


if __name__ == '__main__':
    main()
