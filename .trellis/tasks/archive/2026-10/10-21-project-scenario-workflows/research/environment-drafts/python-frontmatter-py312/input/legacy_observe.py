"""观察固定版文档元数据业务与格式往返边界。"""
import inspect
import io
import json
from pathlib import Path
import frontmatter
from frontmatter import Post
from frontmatter.default_handlers import JSONHandler, TOMLHandler, YAMLHandler


def capture(operation):
    """记录边界调用。@param operation 无参操作。@return 实际结果或异常。"""
    try:
        return {'result':operation()}
    except Exception as error:
        return {'exception':type(error).__name__,'message':str(error)}


text='---\ntitle: 资料整理周报\nauthor: 小林\ntags:\n  - 文档\n  - 图片\n---\n\n本周完成归档，下一步核对目录。\n'
post=frontmatter.loads(text)
assert post['title']=='资料整理周报' and post['tags']==['文档','图片']
post['status']='已校对'
frontmatter.dump(post,Path('/tmp/report.md'))
again=frontmatter.load(Path('/tmp/report.md'))
assert again.metadata==post.metadata and again.content==post.content
toml_text='\n+++\ntitle = "资料"\n+++\n正文'
toml_post=frontmatter.loads(toml_text)
json_empty=frontmatter.dumps(Post('正文',handler=JSONHandler()))
json_empty_again=frontmatter.loads(json_empty)
json_compact=frontmatter.dumps(Post('正文',handler=JSONHandler(),title='资料'),indent=None)
json_compact_again=frontmatter.loads(json_compact)
json_nested='{\n"nested": {\n"x": 1\n}\n}\n正文'
observations=[
 {'step':1,'content_key':capture(lambda:frontmatter.loads('---\ncontent: 备用摘要\n---\n正文').metadata),'handler_key':capture(lambda:frontmatter.loads('---\nhandler: notes\n---\n正文').metadata)},
 {'step':2,'input':toml_text,'metadata':toml_post.metadata,'handler':type(toml_post.handler).__name__,'checks':frontmatter.checks(toml_text),'dumped':frontmatter.dumps(toml_post)},
 {'step':3,'empty_json':json_empty,'empty_reloaded_content':json_empty_again.content,'compact_json':json_compact,'compact_reloaded_metadata':json_compact_again.metadata,'compact_reloaded_content':json_compact_again.content,'nested_json':capture(lambda:frontmatter.loads(json_nested).metadata)},
 {'step':4,'non_mapping_yaml':capture(lambda:frontmatter.loads('---\n- 甲\n- 乙\n---\n正文').metadata),'missing_closing_boundary':frontmatter.parse('---\ntitle: 资料')},
 {'step':5,'input':'  缩进正文\n\n','actual_content':frontmatter.loads('  缩进正文\n\n').content},
 {'step':6,'input':'---\n# 编辑说明\ntitle: "资料"\n---\n正文','dumped':frontmatter.dumps(frontmatter.loads('---\n# 编辑说明\ntitle: "资料"\n---\n正文'))},
 {'step':10,'defaults':{'settings':{'theme':'light','lang':'zh'}},'original_metadata':frontmatter.parse('---\nsettings:\n  theme: dark\n---\n正文',settings={'theme':'light','lang':'zh'})[0]},
 {'step':12,'yaml_date_to_json':capture(lambda:frontmatter.dumps(frontmatter.loads('---\ndate: 2026-10-21\n---\n正文'),handler=JSONHandler()))},
 {'step':13,'bytes_load':capture(lambda:frontmatter.load(io.BytesIO(text.encode())).metadata),'bytes_dump':capture(lambda:frontmatter.dump(post,io.BytesIO())),'existing_bytes_post_is_body_only':bytes(post).decode()},
 {'step':15,'global_handler_types':[type(handler).__name__ for handler in frontmatter.handlers],'existing_loads_signature':str(inspect.signature(frontmatter.loads))},
]
envelope_post=Post('正文',title='资料');envelope_post['content']='元数据摘要'
observations.append({'step':16,'existing_flat_to_dict':envelope_post.to_dict(),'original_metadata':envelope_post.metadata})
for number,name in [(7,'parse_with_locations'),(8,'validate_metadata'),(9,'get_path'),(11,'migrate_metadata'),(14,'read_frontmatter'),(17,'update_file'),(18,'load_records'),(19,'DocumentCatalog'),(20,'main')]:
 observations.append({'step':number,'proposed_entry':name,'on_module':hasattr(frontmatter,name),'on_post':hasattr(Post,name),'note':'原模块/实际Post/handler源码对照后的业务增强提案'})
print(json.dumps({'source_commit':Path('/evidence/revision.txt').read_text().strip(),'module':frontmatter.__file__,'scenario':{'input':text,'metadata':again.metadata,'content':again.content,'written_file':'/tmp/report.md','roundtrip_equal':True},'observations':sorted(observations,key=lambda item:item['step'])},ensure_ascii=False))
