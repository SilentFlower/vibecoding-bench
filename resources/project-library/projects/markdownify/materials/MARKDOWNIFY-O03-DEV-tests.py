"Public regression tests for MARKDOWNIFY-O03-DEV; the complete business contract is in materials/MARKDOWNIFY-O03-DEV-contract.md."
from markdownify import markdownify
import pytest

def test_base_url_covers_links_images_sources_and_posters():
    "Verify base url covers links images sources and posters."
    html='<a href="../page">page</a><img src="pic.png" alt="pic"><video poster="/poster"><source src="movie.mp4"></video>'
    actual=markdownify(html,base_url='https://example.test/docs/index.html')
    assert '[page](https://example.test/page)' in actual
    assert '![pic](https://example.test/docs/pic.png)' in actual
    assert '[![](https://example.test/poster)](https://example.test/docs/movie.mp4)' in actual

def test_callback_receives_resolved_value_once_and_can_suppress():
    "Verify callback receives resolved value once and can suppress."
    seen=[]
    def transform(url,kind):
        seen.append((url,kind));return None if kind=='image' else url+'?tag'
    result=markdownify('<a href="one">a</a><img src="two" alt="i"><video src="three" poster="four"></video>',base_url='https://e.test/',url_transform=transform)
    assert seen==[('https://e.test/one','link'),('https://e.test/two','image'),('https://e.test/three','video'),('https://e.test/four','poster')]
    assert '[a](https://e.test/one?tag)' in result and '![i]()' in result

def test_fragment_empty_absolute_and_invalid_callback_results():
    "Verify fragment empty absolute and invalid callback results."
    seen=[]
    result=markdownify('<a href="#part">local</a><a href="">empty</a><a href="mailto:a@b">mail</a>',base_url='https://e.test/x',url_transform=lambda url,kind:seen.append(url) or url)
    assert '[local](#part)' in result and 'empty' in result and seen==['#part','mailto:a@b']
    with pytest.raises(TypeError):markdownify('<a href="x">x</a>',url_transform=lambda *args:42)
