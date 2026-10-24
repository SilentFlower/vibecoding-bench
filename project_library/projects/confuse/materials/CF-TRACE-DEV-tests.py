"Public regression tests for CF-TRACE-DEV; the complete business contract is in materials/CF-TRACE-DEV-contract.md."
from confuse import RootView,ConfigSource
from confuse.trace import trace_sources

def test_order_metadata_and_no_values_by_default():
    high=ConfigSource({'v':1},filename='/tmp/high.yaml',base_for_paths=True)
    low=ConfigSource({'v':2},default=True);view=RootView([high,low]);rows=trace_sources(view['v'])
    assert rows[0].filename=='/tmp/high.yaml' and rows[0].base_for_paths and rows[0].is_first
    assert rows[1].default and not rows[1].is_first and rows[1].priority==1
    assert all(row.value is None for row in rows)

def test_missing_view_returns_no_sources():
    assert trace_sources(RootView([ConfigSource({})])['missing'])==()

def test_included_values_are_detached_and_redacted():
    source=ConfigSource({'v':[{'secret':'token','name':'a'}]});view=RootView([source])
    view['v'][0]['secret'].redact=True;row=trace_sources(view['v'],include_values=True)[0]
    source['v'][0]['name']='b'
    assert row.value[0]['secret']=='REDACTED' and row.value[0]['name']=='a'

def test_mapping_trace_preserves_each_actual_source_contribution():
    view=RootView([ConfigSource({'v':{'a':1}}),ConfigSource({'v':{'b':2}})])
    rows=trace_sources(view['v'],include_values=True)
    assert dict(rows[0].value)=={'a':1} and dict(rows[1].value)=={'b':2}
