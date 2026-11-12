"""通过真实终端接收合成测试指令，只回传标记与状态，不落终端原文。"""
import errno
import fcntl
import json
import os
import pty
import re
import select
import signal
import struct
import subprocess
import sys
import termios
import time


def emit(frame):
    """发送测试回执。@param frame 安全状态对象。@return 无。"""
    print(json.dumps(frame, ensure_ascii=False), flush=True)


running = True


def stop(_number, _frame):
    """请求收口自己创建的终端。@param _number 信号。@param _frame 调用帧。@return 无。"""
    global running
    running = False


signal.signal(signal.SIGTERM, stop)
label = sys.argv[1]
master, slave = pty.openpty()
fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 40, 180, 0, 0))
child = subprocess.Popen(sys.argv[2:], stdin=slave, stdout=slave, stderr=slave, close_fds=True, start_new_session=True)
os.close(slave)
emit({'type': 'started', 'pid': child.pid})
started = time.monotonic()
output = bytearray()
answered = set()
markers = set()
foreign = False
billing_at = None
try:
    while running and time.monotonic() - started < 120:
        readable, _, _ = select.select([master, sys.stdin], [], [], 0.05)
        if sys.stdin in readable:
            line = sys.stdin.readline()
            if not line:
                break
            command = json.loads(line)
            if command['type'] == 'prompt':
                # 取消后官方会把未完成输入恢复到编辑框；新轮次先清空，避免拼成同一条输入。
                os.write(master, b'\x15')
                time.sleep(0.05)
                os.write(master, command['text'].encode('utf-8') + b'\r')
            elif command['type'] == 'cancel':
                os.write(master, b'\x1b')
            elif command['type'] == 'kill':
                os.killpg(child.pid, signal.SIGKILL)
            elif command['type'] == 'close':
                break
            else:
                raise ValueError('测试终端指令未知')
            emit({'type': 'action', 'action': command['type']})
        if master in readable:
            try:
                block = os.read(master, 65536)
            except OSError as error:
                if error.errno == errno.EIO:
                    break
                raise
            if not block:
                break
            output.extend(block)
            if len(output) > 4 * 1024 * 1024:
                raise RuntimeError('隔离终端输出超限')
            if b'\x1b[6n' in block:
                os.write(master, b'\x1b[1;1R')
            plain = re.sub(r'\x1b\][^\x07]*(?:\x07|\x1b\\)', '', output.decode('utf-8', errors='replace'))
            plain = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', plain)
            compact = re.sub(r'\s+', '', plain).lower()
            if 'doyouwanttousethisapikey' in compact and 'key' not in answered:
                os.write(master, b'\x1b[A')
                time.sleep(0.2)
                os.write(master, b'\r')
                answered.add('key')
            elif ('trustthefiles' in compact or 'yes,itrustthisfolder' in compact or 'isthisaprojectyoucreated' in compact) and 'trust' not in answered:
                os.write(master, b'\r')
                answered.add('trust')
            elif ('choosethetheme' in compact or 'choosethetextstyle' in compact) and 'theme' not in answered:
                os.write(master, b'\r')
                answered.add('theme')
            if 'auto-mode-classifier-billing' in plain and 'entertocontinue' in compact and 'billing_notice' not in answered and billing_at is None:
                # 官方输入保护会丢弃过早的 Enter；延迟只用于告知页，不制造故障竞争。
                billing_at = time.monotonic() + 1.6
            foreign = foreign or ('ISO_' + ('B' if label == 'A' else 'A') + '_') in plain
            for marker in re.findall(r'ISO_[AB]_[A-Z0-9_]+', plain):
                if marker not in markers:
                    markers.add(marker)
                    emit({'type': 'marker', 'value': marker})
        if billing_at is not None and time.monotonic() >= billing_at:
            os.write(master, b'\r')
            answered.add('billing_notice')
            billing_at = None
        if child.poll() is not None:
            break
finally:
    if child.poll() is None:
        os.killpg(child.pid, signal.SIGTERM)
    try:
        child.wait(timeout=2)
    except subprocess.TimeoutExpired:
        os.killpg(child.pid, signal.SIGKILL)
        child.wait()
    os.close(master)
emit({'type': 'exit', 'pid': child.pid, 'code': child.returncode, 'foreignMarkerSeen': foreign, 'markers': sorted(markers)})
