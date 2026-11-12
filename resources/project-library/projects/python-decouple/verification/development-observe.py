"""独立文件矩阵：UTF-8别名、空BOM、注释及INI/ENV值保真。"""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import decouple
from decouple import Config, RepositoryEnv, RepositoryIni


def observations():
    """用真实临时字节文件测试两个仓库入口。@return 业务事实。"""
    facts = {'env_aliases': True, 'ini_aliases': True, 'empty_and_comment': True,
        'embedded_marker_preserved': True, 'explicit_encoding_and_errors': True}
    with TemporaryDirectory() as root:
        path = Path(root) / 'settings'
        for encoding in ('UTF-8', 'utf8', 'utf_8', 'utf-8-sig'):
            for cls, head, field in ((RepositoryEnv, '', 'DC_PRIVATE'), (RepositoryIni, '[settings]\n', 'DC_PRIVATE')):
                path.write_bytes(b'\xef\xbb\xbf' + (head + field + '=雪山\ufefftail\n').encode())
                key = 'env_aliases' if cls is RepositoryEnv else 'ini_aliases'
                try:
                    facts[key] &= Config(cls(str(path), encoding=encoding))(field) == '雪山\ufefftail'
                except Exception:
                    facts[key] = False
        for body in (b'\xef\xbb\xbf', b'\xef\xbb\xbf#comment\nDC_PRIVATE=9\n'):
            path.write_bytes(body)
            try:
                config = Config(RepositoryEnv(str(path)))
                facts['empty_and_comment'] &= config('DC_PRIVATE', default='missing') == ('9' if b'=9' in body else 'missing')
            except Exception:
                facts['empty_and_comment'] = False
        path.write_text('DC_PRIVATE=before\ufeffafter\n\ufeffliteral=value\n', encoding='utf-8')
        config = Config(RepositoryEnv(str(path)))
        facts['embedded_marker_preserved'] = config('DC_PRIVATE') == 'before\ufeffafter' and config('\ufeffliteral') == 'value'
        path.write_bytes('DC_PRIVATE=jalapeño\n'.encode('latin-1'))
        facts['explicit_encoding_and_errors'] &= Config(RepositoryEnv(str(path), encoding='latin-1'))('DC_PRIVATE') == 'jalapeño'
        path.write_bytes(b'DC_PRIVATE=\xff\n')
        try:
            RepositoryEnv(str(path))
            facts['explicit_encoding_and_errors'] = False
        except UnicodeDecodeError:
            pass
    return facts


print(json.dumps({'candidate_import': Path(decouple.__file__).resolve().is_relative_to(Path(os.environ['PROJECT_CANDIDATE_ROOT']) / 'library'), **observations()}))
