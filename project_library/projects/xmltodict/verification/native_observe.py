"""直接观察订单结构、XML输出及输入消费边界，不用答案文本代替程序。"""
from __future__ import annotations

import json
import os
import sys
from io import BytesIO
from pathlib import Path
from xml.etree.ElementTree import fromstring
from xml.parsers.expat import ExpatError

import xmltodict
from xmltodict import ParsingInterrupted, parse, unparse


SINGLE = '<orders><order id="A"><qty>2</qty><label>咖啡</label></order></orders>'
NAMESPACED = '<o:orders xmlns:o="urn:bench:orders"><o:order id="A"><o:qty>2</o:qty></o:order></o:orders>'


def rejects(function, exception: type[Exception]) -> bool:
    """只接受约定异常类型。@param function 调用。@param exception 异常类。@return 是否拒绝。"""
    try:
        function()
    except exception:
        return True
    return False


def structure_observations() -> dict:
    """观察单多订单、属性及应用业务验证边界。@return 实际结构事实。"""
    single = parse(SINGLE)
    multiple = parse('<orders><order id="A"/><order id="B"/></orders>')
    forced = parse(SINGLE, force_list=('order',))
    selected = parse(SINGLE, force_list=lambda path, key, value:
        key == 'order' and bool(path) and path[-1][0] == 'orders')
    invalid_quantity = parse('<orders><order><qty>many</qty></order></orders>')
    return {'attribute_text_shape': single['orders']['order'] == {
                '@id': 'A', 'qty': '2', 'label': '咖啡'},
        'single_multiple_shape': isinstance(single['orders']['order'], dict)
            and isinstance(multiple['orders']['order'], list),
        'existing_force_list': forced == selected
            and forced['orders']['order'] == [single['orders']['order']],
        'business_validation_separate': invalid_quantity['orders']['order']['qty'] == 'many'
            and rejects(lambda: int(invalid_quantity['orders']['order']['qty']), ValueError)}


def namespace_observations() -> dict:
    """核真实URI展开与已有映射，不假设保留词法前缀。@return 命名空间事实。"""
    ordinary = parse(NAMESPACED)
    expanded = parse(NAMESPACED, process_namespaces=True)
    short = parse(NAMESPACED, process_namespaces=True, namespaces={'urn:bench:orders': 'ord'})
    removed = parse(NAMESPACED, process_namespaces=True, namespaces={'urn:bench:orders': None})
    return {'uri_keys_are_observed': ordinary['o:orders']['o:order']['o:qty'] == '2'
            and expanded['urn:bench:orders:orders']['urn:bench:orders:order']['urn:bench:orders:qty'] == '2',
        'existing_namespace_mapping': short['ord:orders']['ord:order']['ord:qty'] == '2'
            and removed['orders']['order']['qty'] == '2'}


def output_observations() -> dict:
    """由标准库独立检查实际输出，避免用库自己的逆操作自证。@return 输出事实。"""
    empty = fromstring(unparse({'root': {'omitted': [], 'none': None,
        'explicit': [None], 'text': ['']}}))
    mixed = '<p>before<b>bold</b>after<i>italic</i>end</p>'
    rewritten = unparse(parse(mixed))
    original_text = ''.join(fromstring(mixed).itertext())
    rewritten_text = ''.join(fromstring(rewritten).itertext())
    return {'empty_list_omitted': empty.find('omitted') is None,
        'explicit_empty_elements': all(empty.find(name) is not None
            for name in ('none', 'explicit', 'text')),
        'mixed_content_not_lexical_roundtrip': original_text == 'beforeboldafteritalicend'
            and rewritten_text != original_text
            and all(part in rewritten_text for part in ('before', 'bold', 'after', 'italic', 'end'))}


def streaming_observations() -> dict:
    """核完整回调消费与立即停止，不把分块输入当返回迭代器。@return 消费事实。"""
    chunks = ['<orders>', '<order id="A"><qty>2</qty></order>',
        '<order id="B"><qty>3</qty></order>', '</orders>']
    received = []

    def collect(path, item):
        """保存稳定路径副本。@param path 当前路径。@param item 一项。@return 继续标记。"""
        received.append((tuple(name for name, attributes in path), item))
        return True

    returned = parse((chunk for chunk in chunks), item_depth=2, item_callback=collect)
    consumed = []

    def source():
        """记录实际消费到的位置。@return 分块生成器。"""
        for number, chunk in enumerate(chunks):
            consumed.append(number)
            yield chunk

    stopped = rejects(lambda: parse(source(), item_depth=2,
        item_callback=lambda path, item: False), ParsingInterrupted)
    return {'item_callbacks_observed': returned is None
            and [item['@id'] for path, item in received] == ['A', 'B']
            and all(path == ('orders', 'order') for path, item in received),
        'callback_stops_source': stopped and consumed == [0, 1]}


def iterator_observations() -> dict:
    """以输入、异常和消费矩阵验证增强合同。@return 原版与增强可区分的事实。"""
    expected = parse(SINGLE)
    chunks = [SINGLE[:12], SINGLE[12:]]
    generator_ok = parse((chunk for chunk in chunks)) == expected
    iterator_rejected = rejects(lambda: parse(iter(chunks)), TypeError)
    result = {'generator_input_preserved': generator_ok,
        'ordinary_iterator_rejected_original': iterator_rejected}
    if iterator_rejected:
        result.update({field: False for field in ('ordinary_iterators_supported',
            'utf8_boundaries_preserved', 'whole_document_inputs_preserved',
            'iterator_errors_preserved', 'callback_stops_iterator', 'namespace_options_preserved')})
        return result

    class Chunks:
        """普通同步迭代器，不属于生成器。"""

        def __init__(self, values):
            """保留底层迭代器。@param values 分块。@return None。"""
            self.values = iter(values)

        def __iter__(self):
            """返回自身。@return 同步迭代器。"""
            return self

        def __next__(self):
            """读取下一个分块。@return 原分块。"""
            return next(self.values)

    class BrokenChunks(Chunks):
        """在已读取前缀后保留真实源错误。"""

        def __next__(self):
            """在第二次取值时报错。@return 首个分块。"""
            value = super().__next__()
            if value == 'fail':
                raise RuntimeError('订单输入源中断')
            return value

    raw = SINGLE.encode('utf-8')
    split = raw.index('咖'.encode('utf-8')) + 1
    consumed = []

    class CountingChunks(Chunks):
        """记录普通Iterator的实际读取位置。"""

        def __next__(self):
            """计数后返回下一块。@return 原分块。"""
            value = super().__next__()
            consumed.append(value)
            return value

    stopped = rejects(lambda: parse(CountingChunks(['<orders>', '<order id="A"/>',
        '<order id="B"/>', '</orders>']), item_depth=2,
        item_callback=lambda path, item: False), ParsingInterrupted)
    result.update({
        'ordinary_iterators_supported': parse(iter(chunks)) == expected
            and parse(map(str, chunks)) == expected and parse(Chunks(chunks)) == expected,
        'utf8_boundaries_preserved': parse(iter([raw[:split], raw[split:]])) == expected,
        'whole_document_inputs_preserved': all(parse(value) == expected
            for value in (SINGLE, raw, bytearray(raw), memoryview(raw), BytesIO(raw))),
        'iterator_errors_preserved': rejects(lambda: parse(iter(['<root>', object()])), TypeError)
            and rejects(lambda: parse(BrokenChunks(['<root>', 'fail'])), RuntimeError)
            and rejects(lambda: parse(iter(['<root>'])), ExpatError),
        'callback_stops_iterator': stopped and consumed == ['<orders>', '<order id="A"/>'],
        'namespace_options_preserved': parse(iter([NAMESPACED]), process_namespaces=True,
            namespaces={'urn:bench:orders': None})['orders']['order']['qty'] == '2'})
    return result


def main() -> None:
    """只输出当前任务冻结的独立原生事实。@return None。"""
    task = sys.argv[1]
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    fields = {
        'XD-U01': ('attribute_text_shape', 'single_multiple_shape'),
        'XD-C01': ('existing_force_list',),
        'XD-P01': ('attribute_text_shape', 'business_validation_separate'),
        'XD-C02': ('uri_keys_are_observed', 'existing_namespace_mapping'),
        'XD-U02': ('empty_list_omitted', 'explicit_empty_elements'),
        'XD-C03': ('mixed_content_not_lexical_roundtrip',),
        'XD-D02': ('generator_input_preserved', 'ordinary_iterator_rejected_original'),
        'XD-M01': ('generator_input_preserved', 'ordinary_iterators_supported',
            'utf8_boundaries_preserved', 'whole_document_inputs_preserved',
            'iterator_errors_preserved', 'callback_stops_iterator', 'namespace_options_preserved'),
        'XD-C04': ('item_callbacks_observed', 'callback_stops_source'),
        'XD-P02': ('item_callbacks_observed', 'callback_stops_source')}
    if task in ('XD-U01', 'XD-C01', 'XD-P01'):
        observations = structure_observations()
    elif task == 'XD-C02':
        observations = namespace_observations()
    elif task in ('XD-U02', 'XD-C03'):
        observations = output_observations()
    elif task in ('XD-D02', 'XD-M01'):
        observations = iterator_observations()
    else:
        observations = streaming_observations()
    print(json.dumps({'candidate_import': Path(xmltodict.__file__).resolve() == root / 'library/xmltodict.py',
        **{field: observations[field] for field in fields[task]}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
