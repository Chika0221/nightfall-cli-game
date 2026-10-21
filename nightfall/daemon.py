"""Single writer Unix-socket server. Only the contractor account may connect."""
import argparse
import fcntl
import json
import logging
import os
from pathlib import Path
import pwd
import signal
import socket
import struct
import time

from .engine import Engine

SOCKET = '/run/nightfall/control.sock'
MAX_REQUEST = 16 * 1024


def serve(root='/', private='/var/lib/nightfall', socket_path=SOCKET, user='contractor'):
    player = pwd.getpwnam(user)
    Path(private).mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(private, 0o700)
    lock = open(Path(private) / 'daemon.lock', 'w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    engine = Engine(root, private, player.pw_uid, player.pw_gid)
    path = Path(socket_path)
    path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    os.chown(path, 0 if os.geteuid() == 0 else os.getuid(), player.pw_gid)
    os.chmod(path, 0o660)
    server.listen(8)
    server.settimeout(2)
    running = True
    sessions = {}
    tick = time.monotonic()
    last_save = tick

    def stop(*_):
        nonlocal running
        running = False
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    def process_info(pid):
        try:
            fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
            return int(fields[1]), fields[19], fields[0]
        except (OSError, IndexError, ValueError):
            return None

    def account():
        nonlocal tick, last_save
        now = time.monotonic()
        if sessions:
            engine.state['elapsed'] += now - tick
        tick = now
        for pid, birth in list(sessions.items()):
            info = process_info(pid)
            if info is None or info[1] != birth or info[2] == 'Z':
                sessions.pop(pid, None)
        if now - last_save >= 5:
            engine.save()
            last_save = now

    try:
        while running:
            account()
            try:
                connection, _ = server.accept()
            except socket.timeout:
                continue
            with connection:
                connection.settimeout(5)
                peer_pid, uid, _ = struct.unpack('3i', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                if uid not in (0, player.pw_uid):
                    continue
                try:
                    with connection.makefile('rb') as stream:
                        raw = stream.readline(MAX_REQUEST + 1)
                    if len(raw) > MAX_REQUEST or not raw.endswith(b'\n'):
                        raise ValueError('要求が長すぎるか、改行がありません。')
                    request = json.loads(raw)
                    account()
                    if isinstance(request, dict) and request.get('op') in ('session-start', 'session-stop'):
                        peer = process_info(peer_pid)
                        parent = process_info(peer[0]) if peer else None
                        if request['op'] == 'session-start' and parent:
                            sessions[peer[0]] = parent[1]
                            if engine.state['started'] is None:
                                engine.state['started'] = time.time()
                        elif peer:
                            sessions.pop(peer[0], None)
                        engine.save()
                        response = {'ok': True, 'result': ''}
                    else:
                        response = engine.handle(request)
                    connection.sendall((json.dumps(response, ensure_ascii=True) + '\n').encode())
                except (ValueError, TypeError, KeyError) as exc:
                    connection.sendall((json.dumps({'ok': False, 'message': '[要求エラー] ' + str(exc)[:150]}) + '\n').encode())
                except (BrokenPipeError, ConnectionError, socket.timeout):
                    pass
                except Exception:
                    logging.exception('Manager operation failed')
                    try:
                        connection.sendall(b'{"ok":false,"message":"Manager error: contact the operator."}\n')
                    except OSError:
                        pass
    finally:
        account()
        engine.save()
        engine.close()
        server.close()
        path.unlink(missing_ok=True)
        lock.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default='/')
    parser.add_argument('--private', default='/var/lib/nightfall')
    parser.add_argument('--socket', default=SOCKET)
    parser.add_argument('--user', default='contractor')
    args = parser.parse_args()
    serve(args.root, args.private, args.socket, args.user)


if __name__ == '__main__':
    main()
