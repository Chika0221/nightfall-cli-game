"""Private record service, recoverable checkpoints and bounded submission validation."""
import base64
import gzip
import io
import json
import os
from pathlib import Path, PurePosixPath
import sqlite3
import stat
import tarfile
import zlib

from . import content as c
from .fs import Files, UnsafePath

MIB = 1024 * 1024


class Incomplete(ValueError):
    pass


class Engine:
    def __init__(self, root='/', private='/var/lib/nightfall', uid=None, gid=None):
        self.private = Path(private)
        self.private.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.private, 0o700)
        self.fs = Files(root, uid, gid)
        self.db = sqlite3.connect(self.private / 'state.sqlite3')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS snapshots (stage INTEGER PRIMARY KEY, data TEXT NOT NULL)')
        row = self.db.execute('SELECT data FROM state WHERE id=1').fetchone()
        if row:
            self.state = json.loads(row[0])
            if self.state['scenario'] != c.SCENARIO:
                self.db.close()
                raise ValueError('旧シナリオの保存データです。運営に新しい専用環境の用意を依頼してください。既存の進捗は変更していません。')
        else:
            self.state = dict(scenario=c.SCENARIO, stage=1, cleared=[], records=[],
                              archive=False, core=False, collected=False, decoy=False,
                              started=None, elapsed=0, hints={}, submitted=False,
                              pending={'kind': 'init'})
            self.save()
        self.resume()

    def close(self):
        self.db.close()

    def save(self):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO state VALUES (1, ?)', (json.dumps(self.state),))

    def put(self, files):
        for path, data in files.items():
            self.fs.write(path, data)

    def action(self, kind, **data):
        self.state['pending'] = dict(kind=kind, **data)
        self.save()
        self.resume()

    def resume(self):
        pending = self.state.get('pending')
        if not pending:
            return
        kind = pending['kind']
        if kind == 'init':
            self.fs.mkdir(c.HOME)
            self.fs.mkdir(c.BASE)
            self.put(c.initial_files())
        elif kind == 'record':
            ref = pending['ref']
            self.put(c.record_files(ref))
            if ref not in self.state['records']:
                self.state['records'].append(ref)
            if not self.state['collected']:
                self.state['stage'] = min(8, 1 + len(self.state['records']) + int(self.state['archive']))
        elif kind == 'archive':
            self.put(c.archive_files())
            self.state['archive'] = True
            self.state['stage'] = min(8, 2 + len(self.state['records']))
        elif kind == 'collect':
            self.put(c.recovery_files())
            self.fs.mkdir(c.HOME + '/submission')
            self.fs.mkdir(c.HOME + '/transfer-cache/old')
            self.state['collected'] = True
            self.state['stage'] = 9
        elif kind == 'decoy':
            self.put(c.decoy_files())
            self.state['decoy'] = True
            self.state['stage'] = 10
        elif kind == 'core':
            self.put({c.BASE + '/core/directive.txt': c.DIRECTIVE})
            self.state['core'] = True
        elif kind == 'complete':
            self.put({c.HOME + '/inbox/last-message.txt': c.COMPLETE})
            self.state['submitted'] = True
        elif kind in ('reset', 'rebuild'):
            snapshot = self.load_snapshot(self.state['stage'])
            for path in c.ROOTS:
                self.fs.remove(path)
            for path, data, mode in snapshot:
                if data is None:
                    self.fs.mkdir(path)
                else:
                    self.fs.write(path, base64.b64decode(data), mode)
            # A later checkpoint may contain a player's accidental edits to an old
            # record. Repair published records from private originals, so reset
            # cannot permanently preserve a corrupted clue or signed document.
            self.put(c.initial_files())
            for ref in self.state['records']:
                self.put({p: data for p, data in c.record_files(ref).items()
                          if p.startswith(c.BASE + '/')})
            if self.state['archive']:
                self.put(c.archive_files())
            if self.state['collected']:
                self.put(c.recovery_records())
            if self.state['decoy']:
                self.put(c.decoy_files())
            if self.state['core']:
                self.put({c.BASE + '/core/directive.txt': c.DIRECTIVE})
            if self.state['submitted']:
                self.put({c.HOME + '/inbox/last-message.txt': c.COMPLETE})
        else:
            raise ValueError('未対応の復旧処理です。')
        self.state['cleared'] = list(range(1, 11 if self.state['submitted'] else self.state['stage']))
        if kind not in ('reset', 'rebuild'):
            self.snapshot(self.state['stage'])
        self.state['pending'] = None
        self.save()

    def snapshot(self, stage):
        entries = self.fs.tree(c.HOME) + self.fs.tree(c.BASE)
        encoded = [(p, None if data is None else base64.b64encode(data).decode(), mode)
                   for p, data, mode in entries]
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO snapshots VALUES (?, ?)', (stage, json.dumps(encoded)))

    def load_snapshot(self, stage):
        row = self.db.execute('SELECT data FROM snapshots WHERE stage=?', (stage,)).fetchone()
        if not row:
            raise Incomplete('復元用の保存地点がありません。運営へ連絡してください。')
        return json.loads(row[0])

    def current(self):
        if self.state['submitted']:
            return c.COMPLETE
        areas = ['/srv/nightfall/public', '/srv/nightfall/maintenance']
        if self.state['records']:
            areas.append('/srv/nightfall/records')
        if 'BKP-0210' in self.state['records']:
            areas.append('/srv/nightfall/backups')
        if self.state['archive']:
            areas.append('/srv/nightfall/vault')
        if self.state['core']:
            areas.append('/srv/nightfall/core')
        inbox = '~/inbox/request.txt'
        if self.state['collected']:
            inbox += ', ~/inbox/ren.txt'
        return ('NIGHTFALL MAINTENANCE TERMINAL\nHost: maintenance-03 / User: contractor\n'
                + '受信: ' + inbox + '\n接続済み:\n' + '\n'.join(areas)
                + '\n\n操作: mission help / 記録照会: mission fetch 参照番号')

    def status(self):
        minutes = int(self.state['elapsed'] // 60)
        hints = sum(len(v) for v in self.state['hints'].values())
        records = ', '.join(self.state['records']) or 'なし'
        areas = ['archive'] if self.state['archive'] else []
        if self.state['core']:
            areas.append('core')
        return (f'経過: {minutes}分 / ヒント: {hints}\n取得記録: {records}\n'
                + '認証済み: ' + (', '.join(areas) or 'なし')
                + f"\n保存地点: {self.state['stage']}（練習用番号）"
                + '\n120分は目安です。時間切れによる失敗はありません。')

    def fetch(self, ref):
        if not isinstance(ref, str) or ref not in c.REFS:
            raise Incomplete('該当する参照番号がありません。資料中の表記を確認してください。')
        if ref in self.state['records']:
            return '[取得済み] ' + ref + '\n' + '\n'.join('/' + p for p in c.record_files(ref))
        if self.state['submitted']:
            raise Incomplete('この回線の受付は終了しています。')
        if ref in c.RESTRICTED and not self.state['archive']:
            raise Incomplete('保管庫の認証が必要です。')
        self.action('record', ref=ref)
        return '[記録受信] ' + ref + '\n' + '\n'.join('/' + p for p in c.record_files(ref))

    def config(self):
        config = {}
        for line in self.fs.read(c.HOME + '/recovery/recovery.conf', 4096).decode().splitlines():
            if not line.strip() or line.lstrip().startswith('#'):
                continue
            key, sep, value = line.partition('=')
            key = key.strip()
            if not sep or key not in ('TARGET', 'OUTPUT') or key in config:
                raise Incomplete('recovery.conf は TARGET と OUTPUT を1行ずつ指定してください。')
            config[key] = value.strip()
        if set(config) != {'TARGET', 'OUTPUT'}:
            raise Incomplete('TARGET または OUTPUT がありません。')
        if config['TARGET'] != c.TARGET:
            raise Incomplete('指定先から応答がありません。通信記録と TARGET を確認してください。')
        if config['OUTPUT'] != '/home/contractor/recovery/output':
            raise Incomplete('OUTPUT は /home/contractor/recovery/output に戻してください。')

    def executable(self):
        info = self.fs.info(c.HOME + '/recovery/recover.sh')
        if not stat.S_ISREG(info.st_mode) or not info.st_mode & stat.S_IXUSR:
            raise Incomplete('recover.sh に所有者の実行権限がありません。ls -l と chmod を確認してください。')

    def recover(self):
        if self.state['collected']:
            return '[受信済み] ~/recovery/output/orders.txt'
        if 'LIAISON-04' not in self.state['records']:
            raise Incomplete('回収ツールが接続されていません。')
        self.config()
        self.executable()
        self.action('collect')
        return '[記録受信] ~/recovery/output/orders.txt\n[新着] ~/inbox/ren.txt'

    @staticmethod
    def archive_members(data):
        if len(data) > MIB:
            raise Incomplete('提出アーカイブは圧縮後1 MiB以下にしてください。')
        # Bound the whole decompressed stream, including headers and padding, before parsing.
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(data)) as gz:
                expanded = gz.read(8 * MIB + 1)
            if len(expanded) > 8 * MIB:
                raise Incomplete('提出アーカイブは展開後8 MiB以下にしてください。')
            result = {}
            seen = set()
            with tarfile.open(fileobj=io.BytesIO(expanded), mode='r:') as tf:
                for count, member in enumerate(tf, 1):
                    if count > 100:
                        raise Incomplete('アーカイブは100エントリ以下にしてください。')
                    path = PurePosixPath(member.name)
                    if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] != 'staging' or '\\' in member.name:
                        raise Incomplete('アーカイブに安全でないパスがあります。staging を基準に梱包してください。')
                    normalized = str(path)
                    if normalized in seen:
                        raise Incomplete('アーカイブ内に重複したパスがあります。作り直してください。')
                    seen.add(normalized)
                    if member.isdir():
                        if normalized != 'staging':
                            raise Incomplete('staging 以外のディレクトリは提出しないでください。')
                        continue
                    if not member.isreg() or member.issparse():
                        raise Incomplete('リンク・特殊ファイル・疎ファイルは提出できません。')
                    if len(path.parts) != 2 or member.size > 8 * MIB:
                        raise Incomplete('staging 直下の証拠ファイルだけを提出してください。')
                    stream = tf.extractfile(member)
                    if stream is None:
                        raise Incomplete('アーカイブ内のファイルが読めません。')
                    with stream:
                        body = stream.read(8 * MIB + 1)
                    if len(body) != member.size:
                        raise Incomplete('アーカイブ内のファイルが破損しています。')
                    result[normalized] = body
            return result
        except (tarfile.TarError, EOFError, OSError, zlib.error) as exc:
            raise Incomplete('アーカイブが破損しています。tar -czf で作り直してください。') from exc

    def validate_cache(self, data):
        if self.fs.exists(c.HOME + '/transfer-cache/old'):
            raise Incomplete('transfer-cache/old が残っています。空のディレクトリを整理してください。')
        total = len(data)
        def size(fd, depth=0):
            if depth > 32:
                raise Incomplete('transfer-cache の階層が深すぎます。')
            subtotal = 0
            for name in os.listdir(fd):
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if stat.S_ISREG(info.st_mode):
                    subtotal += info.st_size
                elif stat.S_ISDIR(info.st_mode):
                    child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    try:
                        subtotal += size(child, depth + 1)
                    finally:
                        os.close(child)
                else:
                    raise Incomplete('transfer-cache のリンク・特殊ファイルを取り除いてください。')
                if subtotal > MIB:
                    break
            return subtotal
        if self.fs.exists(c.HOME + '/transfer-cache'):
            with self.fs.directory(self.fs.parts(c.HOME + '/transfer-cache')) as fd:
                total += size(fd)
        if total > MIB:
            raise Incomplete('キャッシュと送信アーカイブの合計が1 MiBを超えています。')

    @staticmethod
    def fields(body, keys):
        lines = body.replace(b'\r\n', b'\n').splitlines()
        parsed = {}
        if len(lines) != len(keys):
            raise Incomplete('設定の行数が送信仕様と一致しません。')
        for line, expected in zip(lines, keys):
            key, sep, value = line.partition(b'=')
            if not sep or key != expected:
                raise Incomplete('設定のキーと順序を送信仕様で確認してください。')
            parsed[key] = value
        return parsed

    def validate_decoy(self):
        data = self.fs.read(c.HOME + '/submission/decoy.tar.gz', MIB)
        members = self.archive_members(data)
        if set(members) != {'staging/plan.txt', 'staging/READY'}:
            raise Incomplete('協力者報告は staging/plan.txt と staging/READY の2点だけにしてください。')
        if members['staging/READY']:
            raise Incomplete('READY は空の通常ファイルにしてください。')
        keys = [b'SOURCE', b'MEETING_POINT', b'MEETING_TIME']
        plan = self.fields(members['staging/plan.txt'], keys)
        if plan != self.fields(c.PLAN, keys):
            raise Incomplete('報告を送信できません。情報源・配置表・受付時刻を照合してください。')
        self.validate_cache(data)

    def validate_submission(self):
        data = self.fs.read(c.HOME + '/submission/evidence.tar.gz', MIB)
        members = self.archive_members(data)
        evidence = dict(c.EVIDENCE, **{'directive.txt': c.DIRECTIVE.encode()})
        expected = set(evidence) | {'manifest.txt', 'report.txt', 'READY'}
        if set(members) != {'staging/' + name for name in expected}:
            raise Incomplete('移送資料の構成が一致しません。maintenance/transport-format.txt を確認してください。')
        for name, baseline in evidence.items():
            if members['staging/' + name] != baseline:
                raise Incomplete(f'{name} の署名が一致しません。原本をコピーしてください。')
        manifest = members['staging/manifest.txt'].replace(b'\r\n', b'\n').splitlines()
        if len(manifest) != len(evidence) or set(manifest) != {n.encode() for n in evidence}:
            raise Incomplete('manifest.txt は原本5点のファイル名を1行ずつ、重複なく記載してください。')
        keys = [b'VEHICLE', b'GATE', b'DEPARTURE', b'PASSENGERS']
        report = self.fields(members['staging/report.txt'], keys)
        baseline = self.fields(c.REPORT, keys)
        if report != baseline:
            raise Incomplete('車両・検問・出発時刻・乗員が移送資料と一致しません。')
        if members['staging/READY']:
            raise Incomplete('READY は空の通常ファイルにしてください。')
        for name, source in dict(c.SOURCES, **{'directive.txt': c.BASE + '/core/directive.txt'}).items():
            if self.fs.read(source) != evidence[name]:
                raise Incomplete('原本の署名が一致しません。mission reset または運営の復旧を利用してください。')
        self.validate_cache(data)

    def check(self):
        if self.state['submitted']:
            return c.COMPLETE
        if self.state['decoy']:
            return '[送信済み] C-17 / 受領票: ~/recovery/output/receipt.txt'
        if not self.state['collected']:
            return '[送信待機] 協力者回線は未接続。資料の照会は mission fetch 参照番号。'
        self.validate_decoy()
        self.action('decoy')
        return '[送信受付] C-17\n受領票: ~/recovery/output/receipt.txt'

    def unlock(self, area, password):
        if area not in ('archive', 'core'):
            raise Incomplete('保管庫は archive または core を指定してください。')
        if self.state[area]:
            return f'{area} は認証済みです。'
        if area == 'archive' and 'BKP-0210' not in self.state['records']:
            raise Incomplete('保守セッションがありません。')
        if area == 'core' and not self.state['decoy']:
            raise Incomplete('一時認証鍵はまだ発行されていません。')
        if not isinstance(password, str):
            return {'prompt': 'パスワード: ', 'secret': True, 'stage': self.state['stage']}
        if password.strip() != (c.PASSWORD if area == 'archive' else c.KEY):
            raise Incomplete('認証できません。パスワードを確認してください。')
        self.action(area)
        return '[認証成功] /srv/nightfall/' + ('vault' if area == 'archive' else 'core')

    def hint_context(self):
        if not self.state['collected']:
            for n, ref in [(1, 'NOAH-R7'), (2, 'BKP-0210')]:
                if ref not in self.state['records']:
                    return n
            if not self.state['archive']:
                return 3
            for n, ref in [(4, 'MAIL-0216'), (5, 'TERM-E5-03'), (6, 'D-204'), (7, 'LIAISON-04')]:
                if ref not in self.state['records']:
                    return n
            return 8
        return 10 if self.state['decoy'] else 9

    def dispatch(self, request):
        self.resume()
        if 'stage' in request and request['stage'] != self.state['stage']:
            raise Incomplete('端末の接続状態が更新されています。操作をやり直してください。')
        op = request.get('op', 'current')
        if op == 'current':
            return self.current()
        if op == 'help':
            return c.HELP
        if op == 'status':
            return self.status()
        if op == 'fetch':
            return self.fetch(request.get('ref'))
        if op == 'check':
            return self.check()
        if op == 'unlock':
            return self.unlock(request.get('area'), request.get('answer'))
        if op == 'recover':
            return self.recover()
        if op in ('hint', 'hints'):
            if op == 'hints':
                return '\n\n'.join(f'手掛かり {key} / ヒント {i + 1}: {c.STAGES[int(key)]["hints"][i]}'
                                      for key, history in self.state['hints'].items() for i in history) or 'まだヒントを見ていません。'
            key = str(self.hint_context())
            history = self.state['hints'].setdefault(key, [])
            if len(history) < 3:
                history.append(len(history))
                self.save()
            return '\n\n'.join(f'ヒント {i + 1}/3: {c.STAGES[int(key)]["hints"][i]}' for i in history)
        if op == 'reset':
            if self.state['submitted']:
                raise Incomplete('回線の受付は終了しています。mission replay N で練習できます。')
            if not request.get('confirmed'):
                return {'confirm': '最後の保存地点へ戻します。以後のファイル編集は失われます。\n'
                        + '\n'.join('/' + p for p in c.ROOTS), 'stage': self.state['stage']}
            self.action('reset')
            return '[復元完了]\n' + self.current()
        if op == 'replay':
            n = request.get('number')
            if type(n) is not int or not 1 <= n <= 10 or not self.db.execute('SELECT 1 FROM snapshots WHERE stage=?', (n,)).fetchone():
                raise Incomplete('到達済みの保存地点番号を指定してください。mission status で現在の番号を確認できます。')
            replay = self.private / 'replay-request.json'
            tmp = self.private / 'replay-request.tmp'
            tmp.write_text(json.dumps({'stage': n}))
            os.replace(tmp, replay)
            return f'保存地点 {n} の練習を予約しました。exit 後に独立した練習環境を開きます。'
        if op == 'submit':
            if self.state['submitted']:
                return c.COMPLETE
            if not self.state['decoy'] or not self.state['core']:
                raise Incomplete('移送命令の認証が必要です。')
            self.validate_submission()
            self.action('complete')
            return c.COMPLETE
        raise Incomplete('不明な操作です。mission help を確認してください。')

    def handle(self, request):
        try:
            if not isinstance(request, dict):
                raise Incomplete('要求はJSONオブジェクトにしてください。')
            result = self.dispatch(request)
            return {'ok': True, 'result': result}
        except Incomplete as exc:
            return {'ok': False, 'message': '[端末] ' + str(exc)}
        except (OSError, UnsafePath, UnicodeError, RecursionError) as exc:
            detail = str(getattr(exc, 'filename', None) or exc)[:200]
            return {'ok': False, 'message': '[環境エラー] ファイルの不足・権限・形式を確認してください。\n'
                    + detail + '\nmission reset で復元できます。ホーム全体の破損は運営へ連絡してください。'}
