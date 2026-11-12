"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import tomlkit
_candidate_source_root = root
business = False
try:
    from tomlkit.files import load_with_digest,atomic_save,StaleDocumentError
    from tempfile import TemporaryDirectory
    from pathlib import Path
    with TemporaryDirectory() as temporary:
        path=Path(temporary)/'config.toml';path.write_bytes(b'# header\r\na=1\r\n')
        document,digest=load_with_digest(path)
        path.unlink()
        rejected=False
        try:
            atomic_save(document,path,expected_digest=digest)
        except StaleDocumentError:
            rejected=True
        link=Path(temporary)/'link.toml';link.symlink_to(path)
        denied=False
        try:
            atomic_save(document,link)
        except ValueError:
            denied=True
        business=rejected and denied and not path.exists()

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(tomlkit.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
