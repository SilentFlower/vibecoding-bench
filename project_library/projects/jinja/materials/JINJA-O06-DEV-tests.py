"Public regression tests for JINJA-O06-DEV; the complete business contract is in materials/JINJA-O06-DEV-contract.md."
from pathlib import Path
from zipfile import ZipFile,Path as ZipPath
from jinja2 import Environment,TemplateNotFound
import pytest

def test_directory_zip_resources_and_template_inheritance(tmp_path):
    "Verify directory zip resources and template inheritance."
    from jinja2.loaders import ResourcesLoader
    files={'base.html':'A{% block body %}{% endblock %}Z','sub/page.html':'{% extends "base.html" %}{% block body %}{{name}}{% endblock %}'}
    root=tmp_path/'root';root.mkdir()
    archive=tmp_path/'templates.zip'
    with ZipFile(archive,'w') as zipped:
        for name,text in files.items():
            path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text);zipped.writestr(name,text)
    with ZipFile(archive) as zipped:
        for resource in [root,ZipPath(zipped)]:
            loader=ResourcesLoader(resource);env=Environment(loader=loader)
            assert env.get_template('sub/page.html').render(name='中文')=='A中文Z' and loader.list_templates()==sorted(files)

def test_content_reload_immutable_and_encoding(tmp_path):
    "Verify content reload immutable and encoding."
    from jinja2.loaders import ResourcesLoader
    path=tmp_path/'page';path.write_text('one');env=Environment(loader=ResourcesLoader(tmp_path));assert env.get_template('page').render()=='one'
    path.write_text('two');assert env.get_template('page').render()=='two'
    stable=Environment(loader=ResourcesLoader(tmp_path,reload='immutable'));assert stable.get_template('page').render()=='two';path.write_text('three');assert stable.get_template('page').render()=='two'
    path.write_bytes(b'\xff')
    with pytest.raises(UnicodeDecodeError):ResourcesLoader(tmp_path).get_source(env,'page')

def test_traversal_symlink_and_inventory_budget(tmp_path):
    "Verify traversal symlink and inventory budget."
    from jinja2.loaders import ResourcesLoader
    root=tmp_path/'root';root.mkdir();outside=tmp_path/'outside';outside.write_text('private');(root/'link').symlink_to(outside)
    loader=ResourcesLoader(root);env=Environment(loader=loader)
    for name in ['../outside','/outside','a\\b','link']:
        with pytest.raises(TemplateNotFound):env.get_template(name)
    (root/'link').unlink();(root/'x').write_text('x')
    with pytest.raises(ValueError):ResourcesLoader(root,max_templates=0).list_templates()
    with pytest.raises(ValueError):ResourcesLoader(root,reload='guess')
