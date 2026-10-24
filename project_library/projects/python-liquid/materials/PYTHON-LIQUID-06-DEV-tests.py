"""本地项目命令交付真实文件，错误不破坏旧输出或源数据。"""
import json
import tempfile
from pathlib import Path
from liquid.project_cli import main

def test_render_include_unicode_and_empty_output_are_real_files():
    """使用实际FileSystemLoader和JSON而非命令假实现。@return None。"""
    with tempfile.TemporaryDirectory() as directory:
        base=Path(directory);root=base/'templates';root.mkdir()
        (root/'report').write_text('Hi {% render "row", name: user %}',encoding='utf-8');(root/'row').write_text('{{name}}',encoding='utf-8')
        data=base/'data.json';data.write_text(json.dumps({'user':'茶'}));out=base/'report.txt'
        argv=['--root',str(root),'--template','report','--data',str(data),'--output',str(out)]
        assert main(argv)==0 and out.read_text()=='Hi 茶'
        (root/'report').write_text('');assert main(argv)==0 and out.read_bytes()==b''

def test_invalid_data_strict_missing_path_escape_and_source_collision_preserve_old():
    """失败前后旧输出、数据、模板保持；无残留临时文件。@return None。"""
    with tempfile.TemporaryDirectory() as directory:
        base=Path(directory);root=base/'templates';root.mkdir();template=root/'report';template.write_text('{{missing}}')
        data=base/'data.json';data.write_text('{}');out=base/'result';out.write_text('old')
        argv=['--root',str(root),'--template','report','--data',str(data),'--output',str(out)]
        assert main(argv)==2 and out.read_text()=='old'
        data.write_text('[]');assert main(argv)==2 and out.read_text()=='old'
        data.write_text('{}');assert main(argv[:-1]+[str(template)])==2 and template.read_text()=='{{missing}}'
        assert not list(base.glob('.liquid-*'))

