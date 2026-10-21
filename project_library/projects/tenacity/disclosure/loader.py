import json
from pathlib import Path
from tempfile import TemporaryDirectory
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_fixed

with TemporaryDirectory() as directory:
    target = Path(directory) / 'config.json'
    target.write_text('{not-json')
    calls, sleeps = [], []
    def load():
        calls.append(1)
        return json.loads(target.read_text())
    controller = Retrying(retry=retry_if_exception_type(FileNotFoundError), stop=stop_after_attempt(3),
        wait=wait_fixed(0.2), sleep=lambda seconds: sleeps.append(float(seconds)), reraise=True)
    controller(load)
