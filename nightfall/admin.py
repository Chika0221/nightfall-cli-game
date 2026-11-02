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
    if type(stage) is not int or not 1 <= stage <= 10:
        raise ValueError('保存地点は1〜10で指定してください。')
    # Canonical investigation order; normal play may retrieve records in another order.
    actions = [('record', 'NOAH-R7'), ('record', 'BKP-0210'), ('archive', None),
               ('record', 'MAIL-0216'), ('record', 'TERM-E5-03'),
               ('record', 'D-204'), ('record', 'LIAISON-04'),
               ('collect', None), ('decoy', None)]
    for kind, ref in actions[:stage - 1]:
        if kind == 'collect':
            engine.fs.write(c.HOME + '/recovery/recovery.conf',
                            'TARGET=liaison-04\nOUTPUT=/home/contractor/recovery/output\n')
            engine.fs.write(c.HOME + '/recovery/recover.sh', c.RECOVER, 0o744)
        if kind == 'decoy':
            engine.fs.remove(c.HOME + '/transfer-cache/old')
            for name in ['part-1.tmp', 'part-2.tmp']:
                engine.fs.remove(c.HOME + '/transfer-cache/' + name)
            engine.fs.write(c.HOME + '/staging/plan.txt', c.PLAN)
            engine.fs.write(c.HOME + '/staging/READY', b'')
            engine.fs.write(c.HOME + '/submission/decoy.tar.gz',
                            c.archive({'staging/plan.txt': c.PLAN, 'staging/READY': b''}))
        engine.action(kind, **({'ref': ref} if ref else {}))


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
