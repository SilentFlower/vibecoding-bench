"""先执行完整冻结回归，再无损压缩全部跳过与预期失败明细。"""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import base64
import gzip
import hashlib
import json

spec = spec_from_file_location('frozen_html5lib_control', Path(__file__).with_name('native_regression.py'))
control = module_from_spec(spec)
spec.loader.exec_module(control)
original_run = control._run


def archived_run(options):
    """保留原控制完成的全部节点比较，只投影已产生的明细数组。

    @param options 原控制CLI参数。
    @return 原结果及全部明细的可逆、有摘要的压缩档案。
    """
    result = original_run(options)
    if 'skip_xfail' not in result:
        return result
    result = dict(result)
    items = result.pop('skip_xfail')
    raw = json.dumps(items, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode('utf-8')
    compressed = gzip.compress(raw, mtime=0)
    result['skip_xfail_archive'] = {
        'encoding': 'canonical-json+gzip+base64', 'count': len(items),
        'raw_bytes': len(raw), 'raw_sha256': hashlib.sha256(raw).hexdigest(),
        'gzip_bytes': len(compressed), 'gzip_sha256': hashlib.sha256(compressed).hexdigest(),
        'data': base64.b64encode(compressed).decode('ascii')}
    # 原控制已逐项比较全部冻结节点；压缩仅防止2MiB日志轮转丢掉准备证明。
    if len(json.dumps(result, ensure_ascii=False, allow_nan=False).encode('utf-8')) > 1024 * 1024:
        raise ValueError('完整回归无损档案超过安全输出预算')
    return result


control._run = archived_run
if __name__ == '__main__':
    control.main()
