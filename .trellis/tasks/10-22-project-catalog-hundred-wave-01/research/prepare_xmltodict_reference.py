"""制作XML输入增强的参考、全量缓冲反例和原版公开测试对照。"""
from __future__ import annotations

from pathlib import Path
from shutil import copytree


WORKSPACE = Path.cwd() / '.deploy/project-catalog-hundred/stage-01'
PUBLIC_TESTS = '''

def test_order_chunk_iterator_and_map_regression():
    """普通同步迭代器和map必须保持原解析结果。@return None。"""
    chunks = ["<orders>", "<order id='A'><qty>2</qty></order>", "</orders>"]
    expected = {"orders": {"order": {"@id": "A", "qty": "2"}}}
    assert parse(iter(chunks)) == expected
    assert parse(map(str, chunks)) == expected


def test_order_utf8_chunk_iterator_regression():
    """字节边界不得截断多字节业务文本。@return None。"""
    raw = "<order>咖啡</order>".encode("utf-8")
    position = raw.index("咖".encode("utf-8")) + 1
    assert parse(iter([raw[:position], raw[position:]])) == {"order": "咖啡"}


def test_order_iterator_callback_stops_consumption_regression():
    """回调拒绝时不得先消费完整输入。@return None。"""
    consumed = []

    def record(chunk):
        """记录实际被请求的分块。@param chunk 分块。@return 原分块。"""
        consumed.append(chunk)
        return chunk

    chunks = ["<orders>", "<order id='A'/>", "<order id='B'/>", "</orders>"]
    with pytest.raises(ParsingInterrupted):
        parse(map(record, chunks), item_depth=2, item_callback=lambda path, item: False)
    assert consumed == chunks[:2]
'''


def main() -> None:
    """只改变两个授权文件，并保留原版控制。@return None。"""
    seed = WORKSPACE / 'drafts/projects/xmltodict/seed'
    reference = WORKSPACE / 'references/xmltodict'
    control = WORKSPACE / 'public-test-controls/xmltodict-original'
    wrong = WORKSPACE / 'wrong-candidates/xmltodict-buffer-all'
    for target in (reference, control, wrong):
        if target.exists():
            raise ValueError('参考或控制目录已存在，拒绝覆盖')
    copytree(seed, reference)
    module = reference / 'library/xmltodict.py'
    original = module.read_text(encoding='utf-8')
    if original.count('from inspect import isgenerator\n') != 1 or original.count('    elif isgenerator(xml_input):\n') != 1:
        raise ValueError('源码锚点与已读定义不一致')
    enhanced = original.replace('from inspect import isgenerator\n',
        'from inspect import isgenerator\nfrom collections.abc import Iterator\n')
    enhanced = enhanced.replace('    elif isgenerator(xml_input):\n',
        '    elif isgenerator(xml_input) or isinstance(xml_input, Iterator):\n')
    module.write_text(enhanced, encoding='utf-8')
    tests = reference / 'library/tests/test_xmltodict.py'
    tests.write_text(tests.read_text(encoding='utf-8') + PUBLIC_TESTS, encoding='utf-8')
    copytree(seed, control)
    (control / 'library/tests/test_xmltodict.py').write_text(tests.read_text(encoding='utf-8'), encoding='utf-8')
    copytree(reference, wrong)
    # 反例保留一般解析成功，但提前耗尽源，违反公开的流式停止合同。
    bad = enhanced.replace('        for chunk in xml_input:\n', '        for chunk in list(xml_input):\n')
    if bad == enhanced:
        raise ValueError('错误候选未形成实际行为差异')
    (wrong / 'library/xmltodict.py').write_text(bad, encoding='utf-8')
    print('XML参考、三条公开测试、原版控制和全量缓冲反例已制作。')


if __name__ == '__main__':
    main()
