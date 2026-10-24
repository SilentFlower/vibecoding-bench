"""公开xml:space局部空白回归。"""
import xmltodict

def test_preserve_inherits_and_default_restores_original_policy():
    text='<r xml:space="preserve"><a>  one  </a><b xml:space="default">  two  </b></r>'
    result=xmltodict.parse(text,respect_xml_space=True)['r']
    assert result['a']=='  one  ' and result['b']['#text']=='two'

def test_siblings_restore_parent_policy():
    result=xmltodict.parse('<r><a xml:space="preserve"> x </a><b> y </b></r>',respect_xml_space=True)['r']
    assert result['a']['#text']==' x ' and result['b']=='y'

def test_default_respects_callers_disabled_strip_and_legacy_stays_same():
    assert xmltodict.parse('<r xml:space="default"> x </r>',respect_xml_space=True,strip_whitespace=False)['r']['#text']==' x '
    assert xmltodict.parse('<r xml:space="preserve"> x </r>')['r']['#text']=='x'

def test_expanded_namespace_and_streaming_callbacks_observe_effective_policy():
    seen=[]
    xmltodict.parse('<r><a xml:space="preserve"> x </a><a> y </a></r>',process_namespaces=True,respect_xml_space=True,item_depth=2,item_callback=lambda path,item:not seen.append(item))
    assert seen[0]['#text']==' x ' and seen[1]=='y'
