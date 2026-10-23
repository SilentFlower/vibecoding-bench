"""用真实 tmux 和合成 Claude 进程验证 Pi 终端驱动的监听、输入和隔离。"""
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


DRIVER = Path(__file__).resolve().parents[1] / 'images/account/projects_cli.py'
SYNTHETIC_CLAUDE = '''#!/usr/bin/env python3
import json,os,sys,termios,tty
from pathlib import Path
home=Path(os.environ['HOME'])
args=sys.argv[1:]
session=args[args.index('--resume')+1] if '--resume' in args else args[args.index('--session-id')+1]
with (home/'launches.jsonl').open('a') as out:
    out.write(json.dumps({'args':args,'session':session})+'\\n')
tty.setraw(sys.stdin.fileno())
os.write(1,b'\x1b[?2004h')
os.write(1,('原会话已恢复\\r\\n' if '--resume' in args else '请选择运行方式\\r\\n> 调查\\r\\n  实施\\r\\n').encode())
data=b''
while True:
    value=os.read(0,1)
    if not value:
        break
    data+=value
    in_paste=b'\x1b[200~' in data and b'\x1b[201~' not in data
    if value==b'\\r' and not in_paste:
        with (home/'inputs.jsonl').open('a') as out:
            out.write(json.dumps({'session':session,'input':data.decode()},ensure_ascii=False)+'\\n')
        os.write(1,'已收到输入\\r\\n'.encode())
        data=b''
'''


@unittest.skipUnless(shutil.which('tmux'), '需要本机 tmux')
class ProjectsTerminalTests(unittest.TestCase):
    """驱动只监督终端，业务按键由外部控制者实际发送。"""

    def setUp(self):
        """建立不连接网络的两个独立账号终端。:return: None。"""
        self.temporary = tempfile.TemporaryDirectory(prefix='projects-tmux-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / 'bin').mkdir()
        executable = self.root / 'bin/claude'
        executable.write_text(SYNTHETIC_CLAUDE)
        executable.chmod(0o755)
        self.processes = []
        self.addCleanup(self.cleanup_processes)

    def cleanup_processes(self):
        """只清理本测试创建的 socket 和驱动。:return: None。"""
        for process, socket in self.processes:
            subprocess.run(['tmux', '-S', str(socket), 'kill-server'], capture_output=True)
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=3)

    def launch(self, account, resume=False):
        """启动真实驱动。:param account: 合成账号。:param resume: 原会话恢复标记。:return: 进程与配置。"""
        home = self.root / account
        home.mkdir(exist_ok=True)
        config = {'socket': str(home / 'tmux.sock'), 'session': 'projects-test',
            'session_id': 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee', 'resume': resume,
            'settings': str(home / 'settings.json'), 'timeout_sec': 30,
            'exit_file': str(home / 'exit'), 'quota_signal': str(home / 'pause.json')}
        (home / 'settings.json').write_text('{}')
        (home / 'config.json').write_text(json.dumps(config))
        process = subprocess.Popen(['python3', str(DRIVER), '--config', str(home / 'config.json')],
            env={**os.environ, 'HOME': str(home), 'PATH': str(self.root / 'bin') + ':' + os.environ['PATH']},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.processes.append((process, home / 'tmux.sock'))
        return process, config

    def screen(self, config):
        """捕获真实终端画面。:param config: 当前 socket 配置。:return: 原生文本。"""
        result = subprocess.run(['tmux', '-S', config['socket'], 'capture-pane', '-p', '-t', config['session']],
            capture_output=True, text=True)
        return result.stdout

    def until(self, predicate):
        """在短期限内等真实进程产生证据。:param predicate: 证据检查。:return: 实际结果。"""
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            value = predicate()
            if value: return value
            time.sleep(0.05)
        self.fail('终端未在期限内产生预期证据')

    def test_menu_and_bracketed_multiline_are_controlled_outside_driver(self):
        """启动后没有自动输入；菜单和多行正文原样到达真正的 TTY。:return: None。"""
        process, config = self.launch('one')
        home = self.root / 'one'
        self.until(lambda: '请选择运行方式' in self.screen(config))
        self.assertFalse((home / 'inputs.jsonl').exists())
        command = ['tmux', '-S', config['socket']]
        subprocess.run([*command, 'send-keys', '-t', config['session'], 'Down', 'Enter'], check=True)
        self.until(lambda: (home / 'inputs.jsonl').exists())
        self.assertIn('\x1b[B', json.loads((home / 'inputs.jsonl').read_text().splitlines()[0])['input'])
        text = '第一段业务目标\n<pasted_content id="middle">完整正文</pasted_content id="middle">\n最后的兼容要求'
        subprocess.run([*command, 'load-buffer', '-b', 'business', '-'], input=text.encode(), check=True)
        subprocess.run([*command, 'paste-buffer', '-p', '-b', 'business', '-t', config['session']], check=True)
        subprocess.run([*command, 'send-keys', '-t', config['session'], 'Enter'], check=True)
        self.until(lambda: len((home / 'inputs.jsonl').read_text().splitlines()) == 2)
        actual = json.loads((home / 'inputs.jsonl').read_text().splitlines()[1])['input']
        self.assertIn(text.replace('\n', '\r'), actual)

    def test_quota_stops_only_owned_terminal_and_resume_uses_exact_session(self):
        """额度暂停只停止原 socket，另一账号继续；恢复仍传原 session。:return: None。"""
        first, one = self.launch('one')
        second, two = self.launch('two')
        self.until(lambda: '请选择运行方式' in self.screen(one) and '请选择运行方式' in self.screen(two))
        Path(one['quota_signal']).write_text('{"status":"quota_wait"}')
        self.assertEqual(43, first.wait(timeout=4))
        self.assertIsNone(second.poll())
        self.assertIn('请选择运行方式', self.screen(two))
        Path(one['quota_signal']).unlink()
        resumed, configuration = self.launch('one', resume=True)
        self.until(lambda: '原会话已恢复' in self.screen(configuration))
        launches = [json.loads(line) for line in (self.root / 'one/launches.jsonl').read_text().splitlines()]
        self.assertEqual(launches[0]['session'], launches[1]['session'])
        self.assertIn('--resume', launches[1]['args'])


if __name__ == '__main__':
    unittest.main()
