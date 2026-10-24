"""JSONL逐记录编码和写入，不能先物化整条输入。"""
import io
import json
import pytest
from box import BoxList


def test_bounded_first_record():
    """首条编码只读取首条输入，提前关闭不消费尾部。@return None。"""
    seen = []
    def records():
        """大流的可证伪模拟。@return 记录迭代器。"""
        for number in range(100000):
            seen.append(number)
            yield {'id': number}
    lines = BoxList.iter_jsonl_records(records())
    assert json.loads(next(lines)) == {'id': 0}
    lines.close()
    assert seen == [0]


def test_write_file_and_owned_stream(tmp_path):
    """逐行原生读取一致，外部流继续可用。@param tmp_path 临时目录。@return None。"""
    rows = BoxList([{'name': '中文\n行'}, {'value': None}])
    stream = io.StringIO()
    assert rows.write_jsonl(stream, ensure_ascii=False) == 2 and not stream.closed
    assert [json.loads(line) for line in stream.getvalue().splitlines()] == rows.to_list()
    path = tmp_path / 'rows.jsonl'
    assert rows.write_jsonl(path) == 2
    assert [json.loads(line) for line in path.read_text().splitlines()] == rows.to_list()


def test_safe_error_line_and_empty():
    """坏记录指明行号，空表输出为空。@return None。"""
    lines = BoxList.iter_jsonl_records([{'x': 1}, {'bad': object()}])
    next(lines)
    with pytest.raises(ValueError, match='2'):
        next(lines)
    assert list(BoxList().iter_jsonl()) == []
