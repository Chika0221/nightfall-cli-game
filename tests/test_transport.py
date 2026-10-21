import fcntl
import json
import os
from pathlib import Path
import pty
import pwd
import select
import socket
import subprocess
import sys
import tempfile
import termios
import time
import unittest

from nightfall.admin import practice
from nightfall.client import request
from nightfall.engine import Engine


class TransportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.root = self.base / 'root'
        self.root.mkdir()
        self.private = self.base / 'private'
        game = Engine(self.root, self.private)
        practice(game, 5)
        game.close()
        self.socket = str(self.base / 'control.sock')
        self.process = subprocess.Popen([sys.executable, '-m', 'nightfall.daemon', '--root', str(self.root), '--private', str(self.private), '--socket', self.socket, '--user', pwd.getpwuid(os.getuid()).pw_name], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for _ in range(100):
            if Path(self.socket).exists():
                break
            if self.process.poll() is not None:
                self.fail(self.process.stderr.read().decode())
            time.sleep(0.02)
        else:
            self.fail('socket did not start')

    def tearDown(self):
        self.process.terminate()
        try:
            self.process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.communicate()
        self.tmp.cleanup()

    def cli(self, name, *args):
        code = f'from nightfall import client; import sys; client.request.__defaults__=(sys.argv.pop(1),); sys.exit(client.{name}())'
        return [sys.executable, '-c', code, self.socket, *args]

    def test_cli_status_and_bad_request_do_not_kill_manager(self):
        result = subprocess.run(self.cli('mission', 'status'), text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('4/10', result.stdout)
        self.assertFalse(request([], self.socket)['ok'])
        self.assertTrue(request({'op': 'current'}, self.socket)['ok'])
        self.assertTrue(request({'op': 'session-start'}, self.socket)['ok'])
        time.sleep(0.05)
        self.assertTrue(request({'op': 'session-stop'}, self.socket)['ok'])

    def test_password_prompt_uses_real_terminal_without_echo(self):
        master, slave = pty.openpty()
        def terminal():
            os.setsid()
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)
        process = subprocess.Popen(self.cli('vault', 'unlock', 'archive'), stdin=slave, stdout=slave, stderr=slave, preexec_fn=terminal)
        os.close(slave)
        output = bytearray()
        try:
            deadline = time.monotonic() + 5
            while 'パスワード: '.encode() not in output:
                if time.monotonic() > deadline:
                    self.fail('password prompt not displayed: ' + output.decode(errors='replace'))
                if select.select([master], [], [], 0.1)[0]:
                    output.extend(os.read(master, 4096))
            self.assertFalse(termios.tcgetattr(master)[3] & termios.ECHO)
            os.write(master, b'cinder-47\n')
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if select.select([master], [], [], 0.1)[0]:
                    try:
                        chunk = os.read(master, 4096)
                    except OSError:
                        break
                    if not chunk:
                        break
                    output.extend(chunk)
                if process.poll() is not None:
                    break
            self.assertEqual(process.wait(timeout=5), 0, output.decode(errors='replace'))
            self.assertNotIn(b'cinder-47', output)
            self.assertIn('認証成功'.encode(), output)
            self.assertIn('[S6/10', request({'op': 'current'}, self.socket)['result'])
        finally:
            os.close(master)
            if process.poll() is None:
                process.kill()
                process.wait()


if __name__ == '__main__':
    unittest.main()
