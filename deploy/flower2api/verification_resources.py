"""观测兼容演练所在Linux主机资源，性能日志与签名证明分别保存。"""
import json
import os
import sys
from pathlib import Path
from threading import Event, Thread


def _snapshot(root: Path) -> dict:
    """读取主机累计CPU与可用内存，guest时间已包含于user/nice，避免重复计数。"""
    lines = (root / 'stat').read_text().splitlines()
    if not lines or not lines[0].split() or lines[0].split()[0] != 'cpu':
        raise ValueError('主机CPU汇总缺失')
    cpu = list(map(int, lines[0].split()[1:9]))
    memory = {parts[0].rstrip(':'): int(parts[1]) * 1024
        for line in (root / 'meminfo').read_text().splitlines() if (parts := line.split())
        and parts[0] in ('MemTotal:', 'MemAvailable:')}
    vmstat = dict(line.split() for line in (root / 'vmstat').read_text().splitlines())
    if (len(cpu) != 8 or min(cpu) < 0 or not 0 <= memory['MemAvailable'] <= memory['MemTotal']
            or memory['MemTotal'] == 0):
        raise ValueError('主机资源计数无效')
    return {'cpu_total': sum(cpu), 'cpu_idle': cpu[3] + cpu[4],
        'cpu_count': sum(line.split()[0][3:].isdigit() for line in lines if line.startswith('cpu')),
        'memory_total': memory['MemTotal'], 'memory_available': memory['MemAvailable'],
        'oom_kill': int(vmstat['oom_kill']) if 'oom_kill' in vmstat else None}


class VerificationResources:
    """采样整个主机的资源并在所有退出路径收口，指标缺失明确记录。"""

    def __init__(self, workers: int, *, proc_root: Path = Path('/proc'), interval: float = 1.0) -> None:
        """建立一次演练观测。

        :param workers: 当前来源并发数，仅用于关联性能日志。
        :param proc_root: Linux资源文件根，测试可提供独立夹具。
        :param interval: 采样间隔秒数。
        :return: None。
        """
        if interval <= 0:
            raise ValueError('资源采样间隔必须为正数')
        self.root, self.interval = proc_root, interval
        self.stopped = Event()
        self.thread = None
        self.previous = None
        self.initial = None
        self.result = {'event': 'flower2api-database-resources', 'scope': 'host',
            'github_actions': os.environ.get('GITHUB_ACTIONS') == 'true', 'workers': workers,
            'available': True, 'samples': 0, 'cpu_count': None, 'cpu_peak_percent': None,
            'memory_total_bytes': None, 'memory_used_start_bytes': None,
            'memory_used_peak_bytes': None, 'memory_used_peak_delta_bytes': None,
            'memory_available_min_bytes': None, 'oom_kill_delta': None}

    def _sample(self) -> None:
        """累积主机峰值；资源文件异常只标记观测失败，原演练继续按原门禁执行。"""
        if not self.result['available']:
            return
        try:
            value = _snapshot(self.root)
            used = value['memory_total'] - value['memory_available']
            if self.initial is None:
                self.initial = value
                self.result.update(cpu_count=value['cpu_count'], memory_total_bytes=value['memory_total'],
                    memory_used_start_bytes=used, memory_used_peak_bytes=used,
                    memory_available_min_bytes=value['memory_available'])
            if self.previous is not None:
                total = value['cpu_total'] - self.previous['cpu_total']
                idle = value['cpu_idle'] - self.previous['cpu_idle']
                if total < 0 or idle < 0 or idle > total:
                    raise ValueError('主机CPU累计计数变化无效')
                if total:
                    peak = self.result['cpu_peak_percent'] or 0
                    self.result['cpu_peak_percent'] = max(peak, round(100 * (total - idle) / total, 2))
            self.result['memory_used_peak_bytes'] = max(self.result['memory_used_peak_bytes'], used)
            self.result['memory_used_peak_delta_bytes'] = max(0,
                self.result['memory_used_peak_bytes'] - self.result['memory_used_start_bytes'])
            self.result['memory_available_min_bytes'] = min(self.result['memory_available_min_bytes'], value['memory_available'])
            if value['oom_kill'] is not None and self.initial['oom_kill'] is not None:
                delta = value['oom_kill'] - self.initial['oom_kill']
                if delta < 0:
                    raise ValueError('主机OOM累计计数变化无效')
                self.result['oom_kill_delta'] = delta
            self.result['samples'] += 1
            self.previous = value
        except (OSError, ValueError, IndexError, KeyError):
            self.result.update(available=False, error='host_resources_unavailable')

    def _run(self) -> None:
        """按间隔采样，停止事件使演练结束时立即退出等待。"""
        while not self.stopped.wait(self.interval):
            self._sample()
            if not self.result['available']:
                break

    def __enter__(self) -> 'VerificationResources':
        """先记录起点再启动采样线程。:return: 当前观测器。"""
        self._sample()
        if self.result['available']:
            self.thread = Thread(target=self._run, name='flower2api-database-resources')
            self.thread.start()
        return self

    def __exit__(self, exception_type, exception, traceback) -> None:
        """收口并输出性能事件，原错误继续传播。

        :param exception_type: 原异常类型。
        :param exception: 原异常对象。
        :param traceback: 原异常栈。
        :return: None。
        """
        self.stopped.set()
        if self.thread is not None:
            self.thread.join()
        self._sample()
        print(json.dumps(self.result, ensure_ascii=False), file=sys.stderr, flush=True)
