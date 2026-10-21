"""Authoritative state machine. No player answer is ever interpreted as code."""
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
            if self.state['scenario'] != 1:
                raise ValueError('未対応のシナリオ版です。運営に連絡してください。')
        else:
            self.state = dict(scenario=1, stage=1, cleared=[], archive=False, core=False,
                              collected=False, started=None, elapsed=0, hints={},
                              submitted=False, pending={'kind': 'advance', 'target': 1})
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

    def transition(self, target):
        self.state['pending'] = {'kind': 'advance', 'target': target}
        self.save()
        self.resume()

    def resume(self):
        pending = self.state.get('pending')
        if not pending:
            return
        kind = pending['kind']
        if kind == 'advance':
            target = pending['target']
            self.fs.mkdir('home/contractor')
            self.fs.mkdir('srv/nightfall')
            self.put(c.stage_files(target))
            if target == 5:
                self.fs.write(c.OUT + '/access-evidence.txt', c.EVIDENCE['access.txt'])
            if target == 7:
                self.fs.write(c.OUT + '/report-diff.txt', c.EVIDENCE['changes.txt'])
            if target == 8:
                self.fs.write(c.OUT + '/destination-counts.txt', c.EVIDENCE['destinations.txt'])
            if target == 9:
                self.fs.mkdir('home/contractor/submission')
                self.fs.mkdir('home/contractor/transfer-cache/old')
            # Save start snapshots before announcing the stage. Repeating this operation
            # after interruption recreates the same transition and never advances twice.
            self.snapshot(target)
            if target > 1 and target - 1 not in self.state['cleared']:
                self.state['cleared'].append(target - 1)
            self.state['stage'] = target
            if target >= 6:
                self.state['archive'] = True
        elif kind == 'collect':
            self.put({c.OUT + '/relay-receipt.txt': c.RECEIPT, c.OUT + '/.keys/final.key': 'ember-204\n'})
            self.state['collected'] = True
        elif kind == 'core':
            self.fs.write('srv/nightfall/core/directive.txt', c.DIRECTIVE)
            self.state['core'] = True
        elif kind in ('reset', 'rebuild'):
            snapshot = self.load_snapshot(self.state['stage'])
            roots = c.OWNED[self.state['stage']] if kind == 'reset' else ['home/contractor', 'srv/nightfall']
            for path in roots:
                self.fs.remove(path)
            for path, data, mode in snapshot:
                if any(path == p or path.startswith(p + '/') for p in roots):
                    if data is None:
                        self.fs.mkdir(path)
                    else:
                        self.fs.write(path, base64.b64decode(data), mode)
            if self.state['stage'] == 8:
                self.state['collected'] = False
            if kind == 'rebuild' and self.state['core']:
                self.fs.write('srv/nightfall/core/directive.txt', c.DIRECTIVE)
        else:
            raise ValueError('未対応の復旧処理です。')
        self.state['pending'] = None
        self.save()

    def snapshot(self, stage):
        entries = self.fs.tree('home/contractor') + self.fs.tree('srv/nightfall')
        if stage == 10:
            # The accepted archive is the authority, even if staging was later edited.
            data = self.fs.read('home/contractor/submission/evidence.tar.gz', MIB)
            accepted = self.archive_members(data)
            roots = c.OWNED[10]
            entries = [entry for entry in entries if not any(entry[0] == p or entry[0].startswith(p + '/') for p in roots)]
            entries += [('home/contractor/staging', None, 0o755), ('home/contractor/submission/evidence.tar.gz', data, 0o644)]
            entries += [('home/contractor/' + path, body, 0o644) for path, body in accepted.items()]
        encoded = [(p, None if data is None else base64.b64encode(data).decode(), mode) for p, data, mode in entries]
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO snapshots VALUES (?, ?)', (stage, json.dumps(encoded)))

    def load_snapshot(self, stage):
        row = self.db.execute('SELECT data FROM snapshots WHERE stage=?', (stage,)).fetchone()
        if not row:
            raise Incomplete('開始時スナップショットがありません。運営へ連絡してください。')
        return json.loads(row[0])

    def current(self):
        n = self.state['stage']
        if self.state['submitted']:
            return c.COMPLETE + '\n\n' + self.status()
        stage = c.STAGES[n]
        paths = ['/home/contractor']
        for threshold, path in [(3, 'staff'), (4, 'logs'), (5, 'backups'), (6, 'vault')]:
            if n >= threshold:
                paths.append('/srv/nightfall/' + path)
        if self.state['core']:
            paths.append('/srv/nightfall/core')
        guide = '\n\n操作の手引き: ' + stage['guide'] if stage['guide'] else ''
        return f"[S{n}/10: {stage['title']}]\n[受信 / Aoki]\n{stage['task']}{guide}\n\n解放済み: " + ', '.join(paths)

    def status(self):
        elapsed = self.state['elapsed']
        minutes = int(elapsed // 60)
        hint_count = sum(len(v) for v in self.state['hints'].values())
        cleared = len(self.state['cleared'])
        mode = '目安の120分を超えています。引き続き練習できます。' if minutes >= 120 else '120分は目安です。時間切れによる失敗はありません。'
        learned = '\n'.join(f"S{n}: {c.STAGES[n]['guide']}" for n in self.state['cleared'] if c.STAGES[n]['guide'])
        return f'クリア: {cleared}/10 / 経過（プレイ時間）: {minutes}分 / ヒント: {hint_count}\n{mode}\n覚えた操作:\n{learned}'

    def require(self, stage):
        if self.state['stage'] != stage or self.state['submitted']:
            raise Incomplete('現在の依頼に対応する操作を実行してください。mission で確認できます。')

    def config(self):
        raw = self.fs.read('home/contractor/recovery/recovery.conf', 4096).decode('utf-8')
        config = {}
        for line in raw.splitlines():
            if not line.strip() or line.lstrip().startswith('#'):
                continue
            key, sep, value = line.partition('=')
            key = key.strip()
            if not sep or key not in ('TARGET', 'OUTPUT') or key in config:
                raise Incomplete('recovery.conf は TARGET と OUTPUT を1行ずつ指定してください。')
            config[key] = value.strip()
        if set(config) != {'TARGET', 'OUTPUT'}:
            raise Incomplete('recovery.conf に TARGET または OUTPUT がありません。')
        if config['TARGET'] != 'relay-07':
            raise Incomplete(f"[回収失敗] 接続先 {config['TARGET'][:80]} は停止しています。通信先の集計結果と recovery.conf を確認してください。")
        if config['OUTPUT'] != '/home/contractor/recovery/output':
            raise Incomplete('OUTPUT は /home/contractor/recovery/output に戻してください。')
        return config

    def executable(self):
        info = self.fs.info('home/contractor/recovery/recover.sh')
        if not stat.S_ISREG(info.st_mode) or not info.st_mode & stat.S_IXUSR:
            raise Incomplete('recover.sh に所有者の実行権限がありません。ls -l と chmod を確認してください。')

    def recover(self):
        if self.state['collected'] and self.state['stage'] >= 9:
            return '回収は完了済みです。'
        self.require(8)
        self.config()
        self.executable()
        self.state['pending'] = {'kind': 'collect'}
        self.save()
        self.resume()
        return '[回収成功] 最終鍵の保管先は受領記録に残した。先に回収済み証拠を持ち出せる形にしてくれ。\nmission check で次へ。'

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

    def validate_submission(self, final=False):
        data = self.fs.read('home/contractor/submission/evidence.tar.gz', MIB)
        # Keep inspection confined to a private temporary directory. Never extract tar paths.
        import tempfile
        with tempfile.TemporaryDirectory(prefix='submission-', dir=self.private) as temporary:
            copy = Path(temporary) / 'evidence.tar.gz'
            copy.write_bytes(data)
            members = self.archive_members(copy.read_bytes())
        evidence = dict(c.EVIDENCE)
        if final:
            evidence['directive.txt'] = c.DIRECTIVE.encode()
        expected = set(evidence) | {'manifest.txt', 'report.txt', 'READY'}
        missing = expected - {PurePosixPath(p).name for p in members}
        if missing:
            name = sorted(missing)[0]
            raise Incomplete(f'staging/{name} がありません。必要なファイルを用意して再梱包してください。')
        if set(members) != {'staging/' + name for name in expected}:
            raise Incomplete(f'アーカイブの通常ファイルは指定の{len(expected)}点だけにしてください。')
        for name, baseline in evidence.items():
            if members['staging/' + name] != baseline:
                raise Incomplete(f'staging/{name} の内容が基準と一致しません。元の証拠をコピーしてください。')
        manifest = members['staging/manifest.txt'].replace(b'\r\n', b'\n').splitlines()
        if len(manifest) != len(evidence) or set(manifest) != {name.encode() for name in evidence}:
            raise Incomplete('manifest.txt は証拠のファイル名を1行ずつ、重複なく記載してください。')
        report = members['staging/report.txt']
        if report not in (c.REPORT, c.REPORT.rstrip(b'\n')):
            if b'TARGET=relay-07' not in report.splitlines():
                raise Incomplete('report.txt に正しい TARGET の行がありません。上書きと追記の違いを確認してください。ヒント: mission hint')
            raise Incomplete('report.txt は CASE=NF-204 と TARGET=relay-07 の2行にしてください。')
        if members['staging/READY']:
            raise Incomplete('READY は空の通常ファイルにしてください。')
        for name, source in c.SOURCE_NAMES.items():
            if self.fs.read(c.OUT + '/' + source) != c.EVIDENCE[name]:
                raise Incomplete(f'元の証拠 {source} を残してください。運営の環境復旧で元に戻せます。')
        if final and self.fs.read('srv/nightfall/core/directive.txt') != c.DIRECTIVE.encode():
            raise Incomplete('元の指示書が変更されています。運営へ復旧を依頼してください。')
        if self.fs.exists('home/contractor/transfer-cache/old'):
            raise Incomplete('transfer-cache/old が残っています。空のディレクトリを整理してください。')
        total = len(data)
        # Bound memory while summing logical file sizes; no file contents are loaded.
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
        if self.fs.exists('home/contractor/transfer-cache'):
            with self.fs.directory(self.fs.parts('home/contractor/transfer-cache')) as fd:
                total += size(fd)
        if total > MIB:
            raise Incomplete('キャッシュと提出アーカイブの合計が1 MiBを超えています。削除可能な一時ファイルを整理してください。')
        return members

    def check(self, answer=None):
        if self.state['submitted']:
            return c.COMPLETE
        n = self.state['stage']
        if n in (5, 10):
            return 'vault unlock archive で認証してください。' if n == 5 else 'vault unlock core で認証し、mission submit で提出してください。'
        if n == 8:
            self.config()
            self.executable()
            if not self.state['collected']:
                raise Incomplete('管理側に回収成功が記録されていません。./recover.sh を実行してください。')
            if self.fs.read(c.OUT + '/relay-receipt.txt') != c.RECEIPT.encode() or self.fs.read(c.OUT + '/.keys/final.key') != b'ember-204\n':
                raise Incomplete('回収成果物が不足しています。./recover.sh を再実行してください。')
        elif n == 9:
            self.validate_submission()
        else:
            valid = {1: ['foothold'], 2: ['nightjar'], 3: ['GLASS'], 4: ['glass-maintenance.tar.gz', '/srv/nightfall/backups/glass-maintenance.tar.gz'], 6: ['NF-204'], 7: ['relay-07']}
            if not isinstance(answer, str):
                return {'prompt': '回答: ', 'stage': n}
            if answer.strip() not in valid[n]:
                raise Incomplete('回答が一致しません。依頼と手がかりを確認してください。必要なら mission hint。')
        self.transition(n + 1)
        return '[確認成功]\n' + self.current()

    def unlock(self, area, password):
        if area not in ('archive', 'core'):
            raise Incomplete('保管庫は archive または core を指定してください。')
        if self.state[area]:
            return f'{area} は解放済みです。'
        self.require(5 if area == 'archive' else 10)
        if not isinstance(password, str):
            return {'prompt': 'パスワード: ', 'secret': True, 'stage': self.state['stage']}
        if password.strip() != ('cinder-47' if area == 'archive' else 'ember-204'):
            raise Incomplete('認証できません。パスワードを確認してください。')
        if area == 'archive':
            self.transition(6)
        else:
            self.state['pending'] = {'kind': 'core'}
            self.save()
            self.resume()
        return '[認証成功]\n' + self.current()

    def dispatch(self, request):
        # stage tags prevent a second terminal's delayed answer from applying to a new stage.
        self.resume()
        if 'stage' in request and request['stage'] != self.state['stage']:
            raise Incomplete('依頼が更新されています。mission で確認してください。')
        op = request.get('op', 'current')
        if op == 'current':
            return self.current()
        if op == 'help':
            return c.HELP
        if op == 'status':
            return self.status()
        if op == 'check':
            return self.check(request.get('answer'))
        if op == 'unlock':
            return self.unlock(request.get('area'), request.get('answer'))
        if op == 'recover':
            return self.recover()
        if op in ('hint', 'hints'):
            stage = str(self.state['stage'])
            history = self.state['hints'].setdefault(stage, [])
            if op == 'hint' and len(history) < 3:
                history.append(len(history))
                self.save()
            if not history:
                return 'まだヒントを見ていません。mission hint で表示できます。'
            hints = c.STAGES[int(stage)]['hints']
            return '\n\n'.join(f'ヒント {i + 1}/3: {hints[i]}' for i in history)
        if op == 'reset':
            if self.state['submitted']:
                raise Incomplete('本編は完了済みです。mission replay N で練習できます。')
            if not request.get('confirmed'):
                return {'confirm': '以下を開始時の状態に戻します。変更は失われます。\n' + '\n'.join('/' + p for p in c.OWNED[self.state['stage']]), 'stage': self.state['stage']}
            self.state['pending'] = {'kind': 'reset'}
            self.save()
            self.resume()
            return '[復元完了]\n' + self.current()
        if op == 'replay':
            n = request.get('number')
            if type(n) is not int or not 1 <= n <= self.state['stage']:
                raise Incomplete('到達済みのステージ番号を指定してください。')
            replay = self.private / 'replay-request.json'
            tmp = self.private / 'replay-request.tmp'
            tmp.write_text(json.dumps({'stage': n}))
            os.replace(tmp, replay)
            return f'S{n} の練習を予約しました。exit でシェルを終了すると、Windowsの起動処理が独立した練習環境を開きます。'
        if op == 'submit':
            if self.state['submitted']:
                return c.COMPLETE
            self.require(10)
            if self.state['cleared'] != list(range(1, 10)) or not self.state['core']:
                raise Incomplete('S9までの完了と core の認証が必要です。')
            self.validate_submission(final=True)
            self.state['submitted'] = True
            self.state['cleared'].append(10)
            self.save()
            return c.COMPLETE + '\n\n' + self.status()
        raise Incomplete('不明な操作です。mission help を確認してください。')

    def handle(self, request):
        try:
            if not isinstance(request, dict):
                raise Incomplete('要求はJSONオブジェクトにしてください。')
            result = self.dispatch(request)
            return {'ok': True, 'result': result}
        except Incomplete as exc:
            return {'ok': False, 'message': '[未完了] ' + str(exc)}
        except (OSError, UnsafePath, UnicodeError, RecursionError) as exc:
            detail = getattr(exc, 'filename', None)
            if detail:
                detail = str(detail)[:200]
            else:
                detail = str(exc)[:200]
            return {'ok': False, 'message': '[環境エラー] ファイルの不足・権限・形式を確認してください。\n' + detail + '\nmission reset で復元できます。ホーム全体の破損は運営へ連絡してください。'}
