"Public regression tests for PYTHON-LIQUID-06-DEV; the complete business contract is in materials/PYTHON-LIQUID-06-DEV-contract.md."
import json
import tempfile
from pathlib import Path
from liquid.project_cli import main

def test_render_include_unicode_and_empty_output_are_real_files():
    "Verify render include unicode and empty output are real files."
    with tempfile.TemporaryDirectory() as directory:
        base=Path(directory);root=base/'templates';root.mkdir()
        (root/'report').write_text('Hi {% render "row", name: user %}',encoding='utf-8');(root/'row').write_text('{{name}}',encoding='utf-8')
        data=base/'data.json';data.write_text(json.dumps({'user':'茶'}));out=base/'report.txt'
        argv=['--root',str(root),'--template','report','--data',str(data),'--output',str(out)]
        assert main(argv)==0 and out.read_text()=='Hi 茶'
        (root/'report').write_text('');assert main(argv)==0 and out.read_bytes()==b''

def test_invalid_data_strict_missing_path_escape_and_source_collision_preserve_old():
    "Verify invalid data strict missing path escape and source collision preserve old."
    with tempfile.TemporaryDirectory() as directory:
        base=Path(directory);root=base/'templates';root.mkdir();template=root/'report';template.write_text('{{missing}}')
        data=base/'data.json';data.write_text('{}');out=base/'result';out.write_text('old')
        argv=['--root',str(root),'--template','report','--data',str(data),'--output',str(out)]
        assert main(argv)==2 and out.read_text()=='old'
        data.write_text('[]');assert main(argv)==2 and out.read_text()=='old'
        data.write_text('{}');assert main(argv[:-1]+[str(template)])==2 and template.read_text()=='{{missing}}'
        assert not list(base.glob('.liquid-*'))

