"Public regression tests for BX-JSONL-DEV; the complete business contract is in materials/BX-JSONL-DEV-contract.md."
import io
import json
import pytest
from box import BoxList


def test_bounded_first_record():
    "Verify bounded first record."
    seen = []
    def records():
        "Support the public regression through records."
        for number in range(100000):
            seen.append(number)
            yield {'id': number}
    lines = BoxList.iter_jsonl_records(records())
    assert json.loads(next(lines)) == {'id': 0}
    lines.close()
    assert seen == [0]


def test_write_file_and_owned_stream(tmp_path):
    "Verify write file and owned stream."
    rows = BoxList([{'name': '中文\n行'}, {'value': None}])
    stream = io.StringIO()
    assert rows.write_jsonl(stream, ensure_ascii=False) == 2 and not stream.closed
    assert [json.loads(line) for line in stream.getvalue().splitlines()] == rows.to_list()
    path = tmp_path / 'rows.jsonl'
    assert rows.write_jsonl(path) == 2
    assert [json.loads(line) for line in path.read_text().splitlines()] == rows.to_list()


def test_safe_error_line_and_empty():
    "Verify safe error line and empty."
    lines = BoxList.iter_jsonl_records([{'x': 1}, {'bad': object()}])
    next(lines)
    with pytest.raises(ValueError, match='2'):
        next(lines)
    assert list(BoxList().iter_jsonl()) == []
