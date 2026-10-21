# Five-second retry window

The last completed outcome is two seconds after RetryCallState.start_time; the planned next wait is four seconds. The strict requirement is not to start another attempt at or after a five-second retry window. Compare upcoming waits four, three and two seconds. An already blocked synchronous function has not produced an outcome yet; do not claim a stop policy can interrupt it. Outer operation deadlines and retry scheduling are different responsibilities.
