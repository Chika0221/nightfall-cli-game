"""Player-facing client. The private engine and scenario are not installed here."""
import argparse
import getpass
import json
import socket
import sys
import warnings

SOCKET = '/run/nightfall/control.sock'


def request(payload, path=SOCKET):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(60)
        connection.connect(path)
        connection.sendall((json.dumps(payload) + '\n').encode())
        with connection.makefile('rb') as stream:
            raw = stream.readline(256 * 1024)
        return json.loads(raw)


def run(payload):
    try:
        response = request(payload)
        result = response.get('result')
        if response['ok'] and isinstance(result, dict):
            if 'confirm' in result:
                print(result['confirm'])
                if input('復元しますか？ [yes/N]: ').strip().lower() != 'yes':
                    print('復元を取り消しました。')
                    return 0
                payload.update(confirmed=True, stage=result['stage'])
            else:
                if result.get('secret'):
                    # Do not silently fall back to echoed stdin when no real terminal exists.
                    with warnings.catch_warnings():
                        warnings.simplefilter('error', getpass.GetPassWarning)
                        answer = getpass.getpass(result['prompt'])
                else:
                    answer = input(result['prompt'])
                payload.update(answer=answer, stage=result['stage'])
            response = request(payload)
        if response['ok']:
            text = response['result']
            if text:
                print(text)
            return 0
        print(response['message'], file=sys.stderr)
        return 1
    except (EOFError, KeyboardInterrupt):
        print('\n中断しました。進捗は保持されます。', file=sys.stderr)
        return 130
    except getpass.GetPassWarning:
        print('パスワードは対話端末から入力してください。', file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError):
        print('ゲーム管理に接続できません。ゲームを起動し直してください。続く場合は運営へ連絡してください。', file=sys.stderr)
        return 1


def mission():
    parser = argparse.ArgumentParser(prog='mission', description='NIGHTFALL ゲーム操作')
    sub = parser.add_subparsers(dest='op')
    for name in ['check', 'hint', 'hints', 'help', 'status', 'reset', 'submit']:
        sub.add_parser(name)
    replay = sub.add_parser('replay')
    replay.add_argument('number', type=int)
    args = parser.parse_args()
    payload = {'op': args.op or 'current'}
    if args.op == 'replay':
        payload['number'] = args.number
    return run(payload)


def vault():
    parser = argparse.ArgumentParser(prog='vault')
    sub = parser.add_subparsers(dest='op', required=True)
    unlock = sub.add_parser('unlock')
    unlock.add_argument('area', choices=['archive', 'core'])
    args = parser.parse_args()
    return run({'op': 'unlock', 'area': args.area})


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] in ('mission', 'vault'):
        entry = sys.argv.pop(1)
        sys.exit(mission() if entry == 'mission' else vault())
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=['recover', 'session-start', 'session-stop'])
    args = parser.parse_args()
    sys.exit(run({'op': args.operation}))
