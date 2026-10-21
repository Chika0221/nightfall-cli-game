"""Operator-only tools. Stop the daemon before mutating saved state."""
import argparse
import json
import os
from pathlib import Path
import pwd

from . import content as c
from .engine import Engine


def practice(engine, stage):
    if engine.state['cleared'] or engine.state['stage'] != 1:
        raise ValueError('練習の初期化には未使用の環境を使ってください。')
    for n in range(2, stage + 1):
        if n == 9:
            engine.state['pending'] = {'kind': 'collect'}
            engine.save()
            engine.resume()
            engine.fs.write('home/contractor/recovery/recovery.conf', 'TARGET=relay-07\nOUTPUT=/home/contractor/recovery/output\n')
            engine.fs.write('home/contractor/recovery/recover.sh', c.RECOVER, 0o744)
        if n == 10:
            engine.fs.remove('home/contractor/transfer-cache/old')
            for name in ['part-1.tmp', 'part-2.tmp']:
                engine.fs.remove('home/contractor/transfer-cache/' + name)
            files = {'staging/' + name: body for name, body in c.EVIDENCE.items()}
            files.update({'staging/manifest.txt': '\n'.join(c.EVIDENCE) + '\n', 'staging/report.txt': c.REPORT, 'staging/READY': b''})
            for name, body in files.items():
                engine.fs.write('home/contractor/' + name, body)
            engine.fs.write('home/contractor/submission/evidence.tar.gz', c.archive(files))
        engine.transition(n)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=['init', 'rebuild', 'take-replay-request', 'identity'])
    parser.add_argument('--stage', type=int, default=1, choices=range(1, 11))
    parser.add_argument('--root', default='/')
    parser.add_argument('--private', default='/var/lib/nightfall')
    parser.add_argument('--user', default='contractor')
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('運営操作にはrootが必要です。Windows側の運営用スクリプトを利用してください。')
    if args.operation == 'identity':
        print('NIGHTFALL-WSL-1')
        return
    if args.operation == 'take-replay-request':
        path = Path(args.private) / 'replay-request.json'
        if path.exists():
            request = json.loads(path.read_text())
            n = request.get('stage')
            if type(n) is int and 1 <= n <= 10:
                print(n)
            path.unlink()
        return
    # Exclude an active daemon and other admin commands from all state mutations.
    import fcntl
    Path(args.private).mkdir(mode=0o700, parents=True, exist_ok=True)
    with open(Path(args.private) / 'daemon.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        user = pwd.getpwnam(args.user)
        engine = Engine(args.root, args.private, user.pw_uid, user.pw_gid)
        try:
            if args.operation == 'init' and args.stage != 1:
                practice(engine, args.stage)
            elif args.operation == 'rebuild':
                engine.state['pending'] = {'kind': 'rebuild'}
                engine.save()
                engine.resume()
        finally:
            engine.close()


if __name__ == '__main__':
    main()
