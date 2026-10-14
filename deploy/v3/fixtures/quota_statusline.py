"""只在隔离演练中保存合成状态栏输入以核对官方字段。"""
import json
import subprocess
import sys
from pathlib import Path
raw=sys.stdin.read()
try:
    payload=json.loads(raw)
    with Path('/lab/statusline.jsonl').open('a') as destination:
        destination.write(json.dumps(payload)+'\n')
except ValueError:
    pass
result=subprocess.run(['/usr/local/bin/v3-cli-quota','--config','/lab/quota-config.json'],input=raw,text=True,capture_output=True)
sys.stdout.write(result.stdout)
if result.stderr:
    with Path('/lab/collector-errors.log').open('a') as destination:
        destination.write(result.stderr)
