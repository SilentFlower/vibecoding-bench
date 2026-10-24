"""显式密度选图作用于实际图片链接且不获取任何资源。"""
from html2text import HTML2Text
import pytest

def convert(text,density,**options):
    """调用真实img转换设置目标密度。@return Markdown。"""
    converter=HTML2Text(baseurl='https://e.test/docs/',bodywidth=0);converter.image_density=density
    for key,value in options.items():setattr(converter,key,value)
    return converter.handle(text)

def test_smallest_sufficient_density_and_largest_fallback_real_url():
    """候选顺序不影响选择，超过最大密度选最大，默认仍用src。@return None。"""
    html='<img src="fallback" alt="A" srcset="large.png 3x, small.png 1x, medium.png 2x">'
    for target,source in [(1,'small'),(1.5,'medium'),(2,'medium'),(4,'large')]:
        assert 'https://e.test/docs/'+source+'.png' in convert(html,target)
    assert '/docs/fallback' in convert(html,None)

def test_implicit_one_fractional_density_missing_src_and_image_modes():
    """无描述符等于1x，可无src，alt/忽略模式不强迫解析用不到的候选。@return None。"""
    assert '/docs/two' in convert('<img alt="A" srcset="one, two 1.5x">',1.2)
    html='<img src="x" alt="Alt" srcset="bad 100w">'
    assert convert(html,2,images_to_alt=True).strip()=='Alt'
    assert convert(html,2,ignore_images=True).strip()==''
    assert "src='two'" in convert('<img src="one" srcset="two 2x">',2,images_as_html=True)

def test_invalid_duplicate_mixed_density_and_data_url_policy():
    """无效/重复/混用描述符明确拒绝，带逗号data集合明确保留原src。@return None。"""
    for value in ['one 1x, two 1x','one 0x','one 100w, two 2x','one 2x,', 'one invalid']:
        with pytest.raises(ValueError):convert('<img src="fallback" srcset="'+value+'">',2)
    for target in [0,-1,True,float('nan'),float('inf')]:
        with pytest.raises(ValueError):convert('<img src="x" srcset="one 1x">',target)
    assert '/docs/fallback' in convert('<img src="fallback" srcset="data:image/png;base64,AAAA 1x, large 2x">',2)
