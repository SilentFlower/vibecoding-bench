import json
from pathlib import Path
from tempfile import TemporaryDirectory
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_fixed

with TemporaryDirectory() as directory:
    path = Path(directory) / 'config.json'
    attempts, sleeps = [], []
    def before(state):
        if state.attempt_number == 3:
            path.write_text(json.dumps({'region': '华东', 'count': 5}))
    def read_config():
        attempts.append(len(attempts) + 1)
        return json.loads(path.read_text())
    controller = Retrying(retry=retry_if_exception_type(FileNotFoundError), stop=stop_after_attempt(3),
        wait=wait_fixed(0.2), sleep=lambda seconds: sleeps.append(float(seconds)), before=before, reraise=True)
    result = controller(read_config)
    print({'result': result, 'attempts': attempts, 'sleeps': sleeps})
