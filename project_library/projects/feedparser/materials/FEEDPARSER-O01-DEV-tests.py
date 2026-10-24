"""JSON Feed修改时间走真实parse入口，不借published兼容别名冒充。"""
import feedparser,json,io

def parse_entry(values):
    """只解析内存JSON Feed，不触发路径/网络猜测。@return 实际条目。"""
    result=feedparser.parse(io.StringIO(json.dumps({'version':'https://jsonfeed.org/version/1.1','title':'T','items':[dict(id='one',content_text='body',**values)]})))
    assert not result.bozo;return result.entries[0]

def test_only_date_modified_creates_real_updated_and_utc_tuple():
    """检查真实字典键及UTC偏移，不使用published fallback。@return None。"""
    entry=parse_entry({'date_modified':'2026-10-24T09:10:11+08:00'})
    assert dict.__contains__(entry,'updated') and dict.__getitem__(entry,'updated')=='2026-10-24T09:10:11+08:00'
    assert entry.updated_parsed[:6]==(2026,10,24,1,10,11)

def test_correct_field_precedes_legacy_spelling_and_legacy_alone_no_keyerror():
    """新旧同在正式字段优先，旧拼写兼容不再读缺失的date_modified。@return None。"""
    entry=parse_entry({'date_modified':'2026-01-01T00:00:00Z','date_updated':'2025-01-01T00:00:00Z'})
    assert entry.updated.startswith('2026')
    assert parse_entry({'date_updated':'2025-01-01T00:00:00Z'}).updated.startswith('2025')

def test_missing_invalid_and_published_fields_have_distinct_actual_keys():
    """非法值保留原字符串及None解析，无修改日期时不写假updated。@return None。"""
    assert not dict.__contains__(parse_entry({'date_published':'2026-01-01T00:00:00Z'}),'updated')
    bad=parse_entry({'date_modified':'not-a-date'});assert bad.updated=='not-a-date' and bad.updated_parsed is None
