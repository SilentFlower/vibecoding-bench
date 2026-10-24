"""真实树链接清单以base解析并保留原始引用，不做网络操作。"""
import html5lib

def test_first_base_applies_to_actual_links_images_styles_and_media():
    """首base覆盖文档路径并解析全部声明资源，第二base不覆盖。@return None。"""
    from html5lib.links import collect_links
    tree=html5lib.parse('<base href="../assets/"><base href="https://ignored/"><a href="page">P</a><img src="pic"><link href="style"><video src="movie" poster="poster"></video>')
    result=collect_links(tree,document_url='https://e.test/docs/current')
    assert result['base_url']=='https://e.test/assets/'
    assert [(row['raw'],row['resolved']) for row in result['links']]==[(value,'https://e.test/assets/'+value) for value in ['page','pic','style','movie','poster']]

def test_fragments_empty_unknown_schemes_srcset_and_duplicate_groups_are_explicit():
    """原URI保留，空地址不伪造，srcset逐候选及无法解析data集合有状态。@return None。"""
    from html5lib.links import collect_links
    tree=html5lib.parse('<a href="#part">A</a><a href="">empty</a><a href="custom:one">custom</a><img src="same" srcset="same 1x, large 2x"><img srcset="data:image/png;base64,AAA 1x">')
    result=collect_links(tree,document_url='https://e.test/doc')
    assert result['links'][0]['resolved']=='https://e.test/doc#part' and result['links'][1]['resolved']==''
    assert result['links'][2]['resolved']=='custom:one'
    assert any(row['attribute']=='srcset' and row['descriptor']=='2x' and row['raw']=='large' for row in result['links'])
    assert any(row['status']=='unparsed_data_srcset' and row['resolved'] is None for row in result['links'])
    assert any(group['resolved']=='https://e.test/same' and len(group['indexes'])==2 for group in result['groups'])

def test_relative_without_base_dom_etree_and_source_immutability():
    """无基准不猜绝对路径，两后端真实结果一致且树不修改。@return None。"""
    from html5lib.links import collect_links
    values=[]
    for backend in ['etree','dom']:
        tree=html5lib.parse('<p><a href="relative">P</a><img src="x"></p>',treebuilder=backend);before=html5lib.serialize(tree,tree=backend)
        values.append(collect_links(tree,treewalker=backend))
        assert html5lib.serialize(tree,tree=backend)==before
    assert values[0]==values[1] and values[0]['links'][0]['resolved']=='relative'

def test_malformed_nonpositive_and_nonfinite_descriptors_are_not_claimed_parsed():
    """仅接收有限正密度或正整数宽度，坏候选保留原串并明确标未解析。@return None。"""
    from html5lib.links import collect_links
    tree=html5lib.parse('<img srcset="a badx, b 0x, c -1x, d 1e999x, e 1.5w, f 0w, g .5x, h 320w, bare">')
    rows=collect_links(tree)['links']
    assert [row['status'] for row in rows]==['unparsed_srcset']*6+['parsed']*3
    assert all(row['resolved'] is None for row in rows[:6])
    assert [(row['raw'],row['descriptor']) for row in rows[6:]]==[('g','.5x'),('h','320w'),('bare',None)]
