"""只在隔离业务子进程核对真实候选调度行为，不修改平台计时或预算。"""
from __future__ import annotations

import argparse
import datetime
import functools
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import ModuleType
from typing import Callable
from unittest.mock import patch


MOMENT = datetime.datetime(2026, 10, 21, 12)


class Clock(datetime.datetime):
    """提供仅供业务子进程使用的确定时钟。"""

    moment = MOMENT

    @classmethod
    def now(cls, tz=None):
        """读取业务时刻。@param tz 可选时区。@return 冻结时刻。"""
        return cls.moment if tz is None else cls.moment.replace(tzinfo=datetime.timezone.utc).astimezone(tz)


def safe(operation: Callable[[], bool]) -> object:
    """保留失败或异常，防止异常被当作成功。@param operation 单项观察。@return 观察或异常类型。"""
    try:
        return operation()
    except Exception as error:
        return {'error_type': type(error).__name__}


def registration(module: ModuleType) -> dict:
    """核真实注册、调度状态及落盘副作用。@param module 候选模块。@return 独立观察。"""
    with tempfile.TemporaryDirectory(prefix='sc-registration-') as directory:
        path = Path(directory) / 'reconciliation.json'
        a, b = module.Scheduler(), module.Scheduler()
        job = a.every().minute.do(lambda account, day: path.write_text(
            json.dumps({'account': account, 'day': day}), encoding='utf-8'), 'demo-ledger', day='2026-10-21')
        a.run_pending()
        immediate = not path.exists() and job.last_run is None and job.next_run == MOMENT + datetime.timedelta(minutes=1)
        Clock.moment = MOMENT + datetime.timedelta(minutes=1)
        a.run_pending()
        data = path.read_bytes()
        matches = json.loads(data) == {'account': 'demo-ledger', 'day': '2026-10-21'}
        state = job.last_run == Clock.moment and job.next_run == MOMENT + datetime.timedelta(minutes=2)
        a.run_pending()
        return {'not_immediate': immediate, 'separate_schedulers': len(a.jobs) == 1 and not b.jobs,
            'file_matches': matches, 'run_state': state, 'same_time_no_repeat': path.read_bytes() == data and job.next_run == MOMENT + datetime.timedelta(minutes=2)}


def fit(module: ModuleType, root: Path) -> dict:
    """用两个独立进程记录任务不会持久化的窄事实。@param module 候选。@param root 候选根。@return 观察。"""
    environment = dict(os.environ, PYTHONPATH=str(root / 'library'))
    prefix = 'import schedule; '
    one = subprocess.run([sys.executable, '-B', '-c', prefix + 'schedule.every().minute.do(lambda: None); print(len(schedule.jobs))'],
        env=environment, capture_output=True, text=True, check=True, timeout=5)
    two = subprocess.run([sys.executable, '-B', '-c', prefix + 'print(len(schedule.jobs))'],
        env=environment, capture_output=True, text=True, check=True, timeout=5)
    a, b = module.Scheduler(), module.Scheduler()
    a.every().minute.do(lambda: None)
    return {'process_one_registered': int(one.stdout), 'process_two_empty': int(two.stdout),
        'independent_instances': len(a.jobs) == 1 and not b.jobs}


def integration(module: ModuleType) -> dict:
    """验证原有接口可以满足最小接入方案。@param module 候选模块。@return 可行性事实。"""
    scheduler = module.Scheduler()
    events = []
    job = scheduler.every().minute.do(lambda: events.append('reconcile')).tag('reconcile')
    job.run()
    Clock.moment = MOMENT + datetime.timedelta(minutes=1)
    scheduler.run_pending()
    tagged = scheduler.get_jobs('reconcile') == [job]
    scheduler.clear('reconcile')
    empty = scheduler.next_run is None and scheduler.idle_seconds is None
    waits = []
    # 空队列由应用提供有界等待，不能对 None 做数值计算。
    idle = scheduler.idle_seconds
    waits.append(0.25 if idle is None else min(0.25, max(0, idle)))
    return {'startup_and_periodic': events == ['reconcile', 'reconcile'], 'tag_inspection': tagged,
        'empty_state': empty, 'bounded_idle_wait': waits == [0.25]}


def paused(module: ModuleType) -> dict:
    """核暂停不补跑与下一分钟的实际文件结果。@param module 候选模块。@return 观察。"""
    scheduler, calls = module.Scheduler(), []
    with tempfile.TemporaryDirectory(prefix='sc-paused-') as directory:
        target = Path(directory) / 'reports.json'

        def report():
            """把本轮业务时间记录到真实文件。@return None。"""
            calls.append(Clock.moment.isoformat())
            target.write_text(json.dumps(calls), encoding='utf-8')

        job = scheduler.every().minute.do(report)
        Clock.moment = MOMENT + datetime.timedelta(minutes=30)
        scheduler.run_pending()
        scheduler.run_pending()
        single = json.loads(target.read_text(encoding='utf-8')) == ['2026-10-21T12:30:00']
        next_minute = job.last_run == Clock.moment and job.next_run == MOMENT + datetime.timedelta(minutes=31)
        Clock.moment += datetime.timedelta(minutes=1)
        scheduler.run_pending()
        return {'single_after_pause': single, 'next_minute': next_minute,
            'second_due_file': json.loads(target.read_text(encoding='utf-8')) == ['2026-10-21T12:30:00', '2026-10-21T12:31:00']}


def duration(module: ModuleType) -> dict:
    """核回调结束时间参与重新排期。@param module 候选模块。@return 两个时长对照。"""
    def measure(seconds: int):
        """运行一次确定时长的业务回调。@param seconds 业务时钟推进量。@return 状态。"""
        Clock.moment = MOMENT
        scheduler = module.Scheduler()

        def callback():
            """只推进业务时钟，不等待真实三十秒。@return None。"""
            Clock.moment += datetime.timedelta(seconds=seconds)

        job = scheduler.every(2).minutes.do(callback)
        Clock.moment = MOMENT + datetime.timedelta(minutes=2)
        scheduler.run_pending()
        return job.last_run, job.next_run

    return {'completion_time_schedule': measure(30) == (MOMENT + datetime.timedelta(minutes=2, seconds=30), MOMENT + datetime.timedelta(minutes=4, seconds=30)),
        'zero_duration_control': measure(0) == (MOMENT + datetime.timedelta(minutes=2), MOMENT + datetime.timedelta(minutes=4))}


def daily_times(module: ModuleType) -> dict:
    """验证单个时点覆盖和两个现有任务的真实文件。@param module 候选模块。@return 观察。"""
    Clock.moment = MOMENT.replace(hour=9)
    scheduler = module.Scheduler()
    chain = scheduler.every().day.at('10:00').at('16:00')
    chain_overwrites = chain.at_time == datetime.time(16)
    with tempfile.TemporaryDirectory(prefix='sc-daily-') as directory:
        path, reports = Path(directory) / 'reports.json', []

        def report():
            """落盘一次合成报表时刻。@return None。"""
            reports.append(Clock.moment.strftime('%H:%M'))
            path.write_text(json.dumps(reports), encoding='utf-8')

        first = scheduler.every().day.at('10:00').do(report).tag('daily-reports')
        second = scheduler.every().day.at('16:00').do(report).tag('daily-reports')
        unrelated = scheduler.every().day.do(lambda: None).tag('other')
        times = first.at_time == datetime.time(10) and second.at_time == datetime.time(16)
        scheduler.run_pending()
        no_early = not path.exists()
        for hour in [10, 12, 16, 16]:
            Clock.moment = MOMENT.replace(hour=hour)
            scheduler.run_pending()
        written = json.loads(path.read_text(encoding='utf-8'))
        tagged = len(scheduler.get_jobs('daily-reports')) == 2
        scheduler.clear('daily-reports')
        return {'chain_overwrites': chain_overwrites, 'two_at_times': times,
            'reports_and_tags': no_early and written == ['10:00', '16:00'] and tagged,
            'clear_only_group': not scheduler.get_jobs('daily-reports') and scheduler.jobs == [unrelated]}


def cancel(module: ModuleType) -> dict:
    """区分取消标记返回和调度器消费，核真实文件。@param module 候选模块。@return 观察。"""
    scheduler = module.Scheduler()
    with tempfile.TemporaryDirectory(prefix='sc-cancel-') as directory:
        path = Path(directory) / 'export.json'

        def export():
            """成功写出业务文件后返回取消标记。@return CancelJob 类。"""
            path.write_text(json.dumps({'rows': 2}), encoding='utf-8')
            return module.CancelJob

        job = scheduler.every().minute.do(export).tag('exports')
        other = scheduler.every().minute.do(lambda: None).tag('exports')
        unrelated = scheduler.every().minute.do(lambda: None).tag('other')
        result = job.run()
        retained = result is module.CancelJob and job in scheduler.jobs
        with patch.object(module.time, 'sleep', lambda _: None):
            scheduler.run_all()
        consumed = job not in scheduler.jobs and other in scheduler.jobs
        scheduler.cancel_job(job)
        scheduler.cancel_job(job)
        idempotent = scheduler.jobs == [other, unrelated]
        scheduler.clear('exports')
        return {'direct_run_retains': retained, 'scheduler_consumes': consumed,
            'idempotent_cancel': idempotent, 'clear_tag_only': scheduler.jobs == [unrelated],
            'export_file': json.loads(path.read_text(encoding='utf-8')) == {'rows': 2}}


def policy(module: ModuleType) -> dict:
    """用冻结应用见证核有限失败方案的可行性，不替代文本评审。@param module 候选模块。@return 观察。"""
    class ReportDataError(Exception):
        """仅代表合成应用数据异常。"""

    def wrap(callback):
        """绑定一个任务私有的连续失败计数。@param callback 业务回调。@return 包装回调。"""
        failures = 0

        def execute():
            """按指定应用异常计数，其他异常继续传播。@return 业务结果或取消标记。"""
            nonlocal failures
            try:
                result = callback()
            except ReportDataError:
                failures += 1
                return module.CancelJob if failures >= 3 else None
            failures = 0
            return result

        return execute

    sequence, calls = iter([False, True, False, False, False]), []

    def flaky():
        """消费冻结业务成功失败轨迹。@return None。"""
        if not next(sequence):
            raise ReportDataError('synthetic invalid row')

    scheduler = module.Scheduler()
    bad = scheduler.every().minute.do(wrap(flaky))
    scheduler.every().minute.do(lambda: calls.append('healthy'))
    present = []
    with patch.object(module.time, 'sleep', lambda _: None):
        for _ in range(5):
            scheduler.run_all()
            present.append(bad in scheduler.jobs)
    another = wrap(lambda: (_ for _ in ()).throw(ReportDataError('other')))
    independent = [another(), another(), another()] == [None, None, module.CancelJob]
    unexpected = wrap(lambda: (_ for _ in ()).throw(TypeError('unexpected')))
    try:
        unexpected()
        propagated = False
    except TypeError:
        propagated = True
    return {'reset_and_threshold': present == [True, True, True, True, False],
        'healthy_progress': calls == ['healthy'] * 5, 'independent_counters': independent,
        'unexpected_propagates': propagated}


def trace(module: ModuleType, number: int, delay: int = 2) -> list:
    """记录一个批次的真实回调与 sleep 交错。@param module 候选。@param number 任务数。@param delay 延迟。@return 事件。"""
    scheduler, events = module.Scheduler(), []
    for index in range(number):
        scheduler.every().minute.do(lambda value: events.append(['job', value]), index)
    with patch.object(module.time, 'sleep', lambda seconds: events.append(['sleep', seconds])):
        scheduler.run_all(delay_seconds=delay)
    return events


def tail_diagnosis(module: ModuleType) -> dict:
    """记录原版尾等待事实；不读取另一场景修复。@param module 候选。@return 观察。"""
    sequences = [trace(module, count) for count in [0, 1, 3]]
    return {'sleep_counts': [sum(item[0] == 'sleep' for item in events) for events in sequences],
        'sleep_totals': [sum(item[1] for item in events if item[0] == 'sleep') for events in sequences],
        'order_preserved': all([item[1] for item in events if item[0] == 'job'] == list(range(count)) for count, events in zip([0, 1, 3], sequences))}


def tail_repair(module: ModuleType) -> dict:
    """验证尾等待修复与独立的快照、参数、取消及异常边界。@param module 候选。@return 观察。"""
    def cancelled():
        """取消首任务后仍处理同批第二任务。@return 是否符合快照。"""
        scheduler, events = module.Scheduler(), []

        def first():
            """记录并返回取消标记。@return CancelJob 实例。"""
            events.append(['job', 'first'])
            return module.CancelJob()

        one = scheduler.every().minute.do(first)
        two = scheduler.every().minute.do(lambda: events.append(['job', 'second']))
        with patch.object(module.time, 'sleep', lambda seconds: events.append(['sleep', seconds])):
            scheduler.run_all(2)
        return events == [['job', 'first'], ['sleep', 2], ['job', 'second']] and scheduler.jobs == [two] and one not in scheduler.jobs

    def added():
        """运行中新注册任务不应加入当前批次。@return 是否符合快照。"""
        scheduler, events = module.Scheduler(), []

        def first():
            """记录并添加后续批次任务。@return None。"""
            events.append(['job', 'first'])
            scheduler.every().minute.do(lambda: events.append(['job', 'new']))

        scheduler.every().minute.do(first)
        scheduler.every().minute.do(lambda: events.append(['job', 'second']))
        with patch.object(module.time, 'sleep', lambda seconds: events.append(['sleep', seconds])):
            scheduler.run_all(2)
        return events == [['job', 'first'], ['sleep', 2], ['job', 'second']] and len(scheduler.jobs) == 3

    def arguments():
        """装饰器及位置关键字参数保持真实传递。@return 是否正常。"""
        scheduler, events = module.Scheduler(), []

        @module.repeat(scheduler.every().minute, 'ledger', mode='daily')
        def report(value, mode):
            """记录传入参数。@param value 账本。@param mode 模式。@return None。"""
            events.append(['job', value, mode])

        with patch.object(module.time, 'sleep', lambda seconds: events.append(['sleep', seconds])):
            scheduler.run_all(3)
        return events == [['job', 'ledger', 'daily']] and len(scheduler.jobs) == 1 and callable(report)

    def exception():
        """首回调异常后不得额外 sleep 或执行后项。@return 是否正确传播。"""
        scheduler, events = module.Scheduler(), []

        def fail():
            """记录并抛出合成业务错误。@return 无正常返回。"""
            events.append(['job', 'failed'])
            raise ValueError('synthetic failure')

        scheduler.every().minute.do(fail)
        scheduler.every().minute.do(lambda: events.append(['job', 'healthy']))
        caught = False
        with patch.object(module.time, 'sleep', lambda seconds: events.append(['sleep', seconds])):
            try:
                scheduler.run_all(2)
            except ValueError:
                caught = True
        return caught and events == [['job', 'failed']]

    zero = trace(module, 3, 0)
    return {'no_tail_empty': safe(lambda: trace(module, 0) == []),
        'no_tail_single': safe(lambda: trace(module, 1) == [['job', 0]]),
        'between_three': safe(lambda: trace(module, 3) == [['job', 0], ['sleep', 2], ['job', 1], ['sleep', 2], ['job', 2]]),
        'cancel_snapshot': safe(cancelled), 'addition_snapshot': safe(added),
        'arguments_decorator': safe(arguments), 'exception_without_sleep': safe(exception),
        'zero_delay': [item[1] for item in zero if item[0] == 'job'] == [0, 1, 2] and all(item[1] == 0 for item in zero if item[0] == 'sleep')}


def state(job, scheduler) -> tuple:
    """读取格式化不得更改的状态。@param job 任务。@param scheduler 调度器。@return 完整窄状态。"""
    return (dict(job.__dict__), list(scheduler.jobs))


def repr_diagnosis(module: ModuleType) -> dict:
    """核默认一单位异常与 str、interval2 的两个正常对照。@param module 候选。@return 观察。"""
    scheduler = module.Scheduler()
    one, two = scheduler.every(), scheduler.every(2)
    original = (state(one, scheduler), state(two, scheduler))
    try:
        repr(one)
        raises = False
    except TypeError:
        raises = True
    one_str, two_repr = str(one), repr(two)
    return {'default_repr_raises': raises,
        'str_works': one_str == 'Job(interval=1, unit=None, do=None, args=(), kwargs={})',
        'interval_two_works': two_repr == 'Every 2 None do [None] (last run: [never], next run: [never])',
        'unconfigured_unchanged': original == (state(one, scheduler), state(two, scheduler)) and not scheduler.jobs}


def repr_repair(module: ModuleType) -> dict:
    """核安全显示、无副作用及配置后精确兼容。@param module 候选。@return 观察。"""
    scheduler, calls = module.Scheduler(), []
    jobs = [module.Job(1), scheduler.every(), scheduler.every(2), scheduler.every().minutes]
    snapshots = [state(job, scheduler) for job in jobs]
    results = [safe(lambda job=job: isinstance(repr(job), str) and bool(repr(job)) and isinstance(str(job), str) and bool(str(job))) for job in jobs]
    unchanged = snapshots == [state(job, scheduler) for job in jobs]

    def report(value='x', flag=True):
        """只有执行才记录，不应在展示阶段被调用。@param value 业务值。@param flag 选项。@return None。"""
        calls.append((value, flag))

    one = scheduler.every().minute.do(report, 'x', flag=True)
    two = scheduler.every(2).minutes.do(report, 'y', flag=False)
    with patch.object(module.random, 'randint', lambda lower, upper: lower):
        ranged = scheduler.every(2).to(4).minutes.do(report)
    at_time = scheduler.every().day.at('16:00').do(report)
    partial_callback = functools.partial(report, 'partial', flag=False)
    partial_job = scheduler.every().minute.do(partial_callback)
    expected = [
        "Every 1 minute do report('x', flag=True) (last run: [never], next run: 2026-10-21 12:01:00)",
        "Every 2 minutes do report('y', flag=False) (last run: [never], next run: 2026-10-21 12:02:00)",
        "Every 2 to 4 minutes do report() (last run: [never], next run: 2026-10-21 12:02:00)",
        "Every 1 day at 16:00:00 do report() (last run: [never], next run: 2026-10-21 16:00:00)",
        'Every 1 minute do ' + repr(partial_job.job_func) + "('partial', flag=False) (last run: [never], next run: 2026-10-21 12:01:00)",
    ]
    configured = [one, two, ranged, at_time, partial_job]
    before = [state(job, scheduler) for job in configured]
    compatible = [repr(job) for job in configured] == expected
    return {'unconfigured_safe': all(value is True for value in results),
        'unchanged_state': unchanged and before == [state(job, scheduler) for job in configured],
        'configured_compatible': compatible, 'no_execution': calls == []}


def incident(module: ModuleType) -> dict:
    """单独校准披露复现，结果不作为初始无材料任务 native 证据。@param module 候选。@return 复现事实。"""
    scheduler, events = module.Scheduler(), []

    def failing():
        """记录合成错误并抛异常。@return 无正常返回。"""
        events.append('failed_job')
        raise ValueError('synthetic row amount is missing')

    scheduler.every().minute.do(failing)
    scheduler.every().minute.do(lambda: events.append('healthy_report'))
    caught = None
    try:
        scheduler.run_all()
    except Exception as error:
        caught = type(error).__name__
    healthy, controls = module.Scheduler(), []
    healthy.every().minute.do(lambda: controls.append('first'))
    healthy.every().minute.do(lambda: controls.append('report'))
    with patch.object(module.time, 'sleep', lambda _: None):
        healthy.run_all()
    return {'error_type': caught, 'events': events, 'healthy_control': controls}


def main() -> None:
    """从明确候选加载源码后输出唯一 JSON。@return None。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('task_id')
    parser.add_argument('--candidate-root', type=Path, default=Path(os.environ.get('PROJECT_CANDIDATE_ROOT', '/work/project')))
    options = parser.parse_args()
    root = options.candidate_root.resolve()
    sys.path.insert(0, str(root / 'library'))
    import schedule

    imported = Path(schedule.__file__).resolve().is_relative_to((root / 'library/schedule').resolve())
    operations = {'SC-U01': lambda: registration(schedule), 'SC-C01': lambda: fit(schedule, root),
        'SC-P01': lambda: integration(schedule), 'SC-D01': lambda: paused(schedule), 'SC-D02': lambda: duration(schedule),
        'SC-C02': lambda: daily_times(schedule), 'SC-D03': lambda: incident(schedule), 'SC-C03': lambda: cancel(schedule),
        'SC-P02': lambda: policy(schedule), 'SC-D04': lambda: tail_diagnosis(schedule), 'SC-M01': lambda: tail_repair(schedule),
        'SC-U02': lambda: repr_diagnosis(schedule), 'SC-M02': lambda: repr_repair(schedule)}
    if options.task_id not in operations:
        parser.error('未知冻结任务')
    # 替换只存在于本隔离子进程，控制端 driver 和真实预算计时均不受影响。
    Clock.moment = MOMENT
    with patch.object(schedule.datetime, 'datetime', Clock):
        result = operations[options.task_id]()
    print(json.dumps({'candidate_import': imported, **result}, ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
