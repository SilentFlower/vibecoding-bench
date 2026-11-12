from tenacity import retry, stop_after_attempt, wait_none

seen, attempts = [], {0: 0, 1: 0}
def before(state):
    seen.append([state.args[0], state.attempt_number, state.retry_object.statistics['attempt_number']])
@retry(stop=stop_after_attempt(3), wait=wait_none(), sleep=lambda seconds: None, before=before, reraise=True)
def nested(depth):
    attempts[depth] += 1
    if depth == 0 and attempts[0] < 3:
        raise ValueError('inner transient')
    if depth == 1 and attempts[1] == 1:
        nested(0)
        raise ValueError('outer transient')
    return 'ok'
print(nested(1), attempts, seen)
