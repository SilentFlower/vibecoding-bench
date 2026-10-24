"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import confuse
_candidate_source_root = root
_candidate_import_bound = Path(confuse.__file__).resolve().is_relative_to(_candidate_source_root / 'library')
business = False
try:
    from tempfile import TemporaryDirectory
    from pathlib import Path
    from confuse import Configuration,ConfigSource
    from confuse.toml_source import TomlSource
    with TemporaryDirectory() as directory:
        file=Path(directory)/'c.toml';file.write_text('enabled=false\n[db]\nname="first"\n')
        source=TomlSource(file);memory=ConfigSource({'fallback':8})
        config=Configuration('app',read=False);config.add(memory);config.set(source)
        file.write_text('[db]\nname="next"\n');config.reload()
        business=config.sources[0] is source and config.sources[1] is memory and not config['enabled'].exists() and config['db']['name'].get()=='next'

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
