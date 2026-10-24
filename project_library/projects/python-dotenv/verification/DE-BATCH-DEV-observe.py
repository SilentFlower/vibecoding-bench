"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import dotenv
_candidate_source_root = root
business = False
try:
    from dotenv.editing import update_keys
    from dotenv import dotenv_values
    from tempfile import TemporaryDirectory
    from pathlib import Path
    from unittest.mock import patch
    import os
    with TemporaryDirectory() as temporary:
        path=Path(temporary)/'config.env'
        original=b'# comment\rKEEP="a\rb"\rDROP=1\r'
        path.write_bytes(original)
        update_keys(path, {'Q':"a'\\b"}, remove=('DROP',))
        success=path.read_bytes().startswith(b'# comment\rKEEP="a\rb"\r') and dotenv_values(path,interpolate=False)['Q']=="a'\\b"
        before=path.read_bytes()
        try:
            with patch('os.replace', side_effect=OSError('synthetic')):
                update_keys(path, {'Q':'again'})
        except OSError:
            pass
        business=success and path.read_bytes()==before and list(Path(temporary).iterdir())==[path]

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(dotenv.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
