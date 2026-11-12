"""通过真实伪终端验证交互 CLI，只输出合成联调结果，不保存终端原文。"""
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

master, slave = pty.openpty()
fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 36, 120, 0, 0))
child = subprocess.Popen(sys.argv[1:], stdin=slave, stdout=slave, stderr=slave, close_fds=True, start_new_session=True)
os.close(slave)
started = time.monotonic()
output = bytearray()
answered = set()
seen = False
plain = ''
try:
    while time.monotonic() - started < 20:
        readable, _, _ = select.select([master], [], [], 0.1)
        if readable:
            try:
                block = os.read(master, 65536)
            except OSError as error:
                if error.errno == errno.EIO:
                    break
                raise
            if not block:
                break
            output.extend(block)
            if len(output) > 2 * 1024 * 1024:
                raise RuntimeError('隔离终端输出超限')
            if b'\x1b[6n' in block:
                os.write(master, b'\x1b[1;1R')
            plain = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', output.decode('utf-8', errors='replace'))
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
            if '本机假池ok' in compact:
                seen = True
                break
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
print(json.dumps({'terminal': True, 'finalSeen': seen, 'actions': sorted(answered), 'exitCode': child.returncode, 'screen': '' if seen else plain[-1800:]}, ensure_ascii=False))
sys.exit(0 if seen else 2)
