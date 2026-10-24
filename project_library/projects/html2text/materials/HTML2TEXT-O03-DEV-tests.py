"Public regression tests for HTML2TEXT-O03-DEV; the complete business contract is in materials/HTML2TEXT-O03-DEV-contract.md."
from html2text import HTML2Text
import pytest

def convert(text,**options):
    "Support the public regression through convert."
    converter=HTML2Text(bodywidth=0);converter.figure_mode='group'
    for key,value in options.items():setattr(converter,key,value)
    return converter.handle(text)

def test_image_alt_caption_and_neighbor_text_stay_distinct():
    "Verify image alt caption and neighbor text stay distinct."
    actual=convert('before<figure><img src="x.png" alt="actual alt"><figcaption>Diagram <em>one</em></figcaption></figure>after')
    assert actual.strip()=='before\n\n![actual alt](x.png)\n\nDiagram _one_\n\nafter'

def test_multiple_nested_figures_and_caption_only_documents_keep_order():
    "Verify multiple nested figures and caption only documents keep order."
    text='<figure><img src="a"><img src="b"><figure><img src="c"><figcaption>Inner</figcaption></figure><figcaption>Outer</figcaption></figure>'
    actual=convert(text)
    assert actual.index('](a)')<actual.index('](b)')<actual.index('](c)')<actual.index('Inner')<actual.index('Outer')
    assert '](a)\n\n![' in actual and convert('<figure><figcaption>Only</figcaption></figure>').strip()=='Only'

def test_image_options_empty_caption_state_reset_and_default_compatibility():
    "Verify image options empty caption state reset and default compatibility."
    text='<figure><img src="x" alt="Alt"><figcaption>Caption</figcaption></figure>'
    assert convert(text,ignore_images=True).strip()=='Caption'
    assert 'Alt\n\nCaption' in convert(text,images_to_alt=True)
    converter=HTML2Text(bodywidth=0);converter.figure_mode='group';converter.handle('<figure><img src="x">')
    assert converter._figure_depth==0 and converter.handle('<p>next</p>').strip()=='next'
    original=HTML2Text(bodywidth=0).handle(text);assert original==convert(text,figure_mode='legacy')
