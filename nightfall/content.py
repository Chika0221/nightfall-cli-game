"""Fixed scenario v1; installed in the private manager package, never on player PATH."""
import difflib
import gzip
import io
import json
import random
import tarfile

HOME = '/home/contractor'
BASE = '/srv/nightfall'
OUT = 'home/contractor/recovery/output'
ACCESS_LINE = '02:14:08 user=aoki project=GLASS action=backup status=OK path=/srv/nightfall/backups/glass-maintenance.tar.gz\n'
BEFORE = '# GLASS 測定報告\nCASE=NF-201 STATUS=NORMAL VALUE=10\nCASE=NF-204 STATUS=CRITICAL VALUE=87\nCASE=NF-209 STATUS=NORMAL VALUE=9\n通信記録: /srv/nightfall/vault/net/transfer-destinations.log\n'
AFTER = BEFORE.replace('STATUS=CRITICAL VALUE=87', 'STATUS=NORMAL VALUE=12')
RECEIPT = '回収成功: TARGET=relay-07\nFinal key: /home/contractor/recovery/output/.keys/final.key\n'
DIRECTIVE = 'DIRECTIVE / INTERNAL ONLY\nCASE=NF-204\nPROJECT=GLASS\n測定値87を12へ変更し、公開報告の判定をNORMALとすること。\n承認: NIGHTFALL Operations Director\n'
EVIDENCE = {
    'access.txt': ACCESS_LINE.encode(),
    'changes.txt': ''.join(difflib.unified_diff(BEFORE.splitlines(True), AFTER.splitlines(True), fromfile='before.txt', tofile='after.txt')).encode(),
    'destinations.txt': b'     24 relay-07\n     15 relay-02\n     12 relay-11\n      9 relay-04\n',
    'receipt.txt': RECEIPT.encode(),
}
SOURCE_NAMES = dict(zip(EVIDENCE, ['access-evidence.txt', 'report-diff.txt', 'destination-counts.txt', 'relay-receipt.txt']))
REPORT = b'CASE=NF-204\nTARGET=relay-07\n'
RECOVER = '''#!/bin/bash
# 設定は実行せず、ゲーム管理側がキーと値として読み取ります。
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
if [ "$here" != /home/contractor/recovery ]; then
  echo '[回収失敗] 元の /home/contractor/recovery/recover.sh を起動してください。' >&2
  exit 1
fi
exec /usr/local/bin/nightfall-recover
'''


def archive(files):
    buffer = io.BytesIO()
    # Both tar and gzip timestamps are fixed for reproducible evidence.
    with gzip.GzipFile(fileobj=buffer, mode='wb', mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode='w') as tf:
            for name, data in sorted(files.items()):
                if isinstance(data, str):
                    data = data.encode()
                member = tarfile.TarInfo(name)
                member.mode = 0o644
                member.size = len(data)
                tf.addfile(member, io.BytesIO(data))
    return buffer.getvalue()


def stage_files(stage):
    home = 'home/contractor/'
    base = 'srv/nightfall/'
    if stage == 1:
        return {
            home + 'README.txt': 'NIGHTFALL MAINTENANCE TERMINAL\nHost: maintenance-03\nUser: contractor\n\n受信メッセージは inbox にある。まず現在地と一覧を確認してくれ。\n依頼: mission / 操作説明: mission help\n',
            home + 'inbox/first-contact.txt': '入れたようだな。俺のアカウントは止められた。だが、記録はまだ残っている。\n明朝には全部消される。\nHandshake: foothold\n表に出せない連絡先はホームに隠した。\n',
        }
    if stage == 2:
        return {home + '.contact': 'Contact phrase: nightjar\n調査対象: aoki\n引き継ぎ記録: handover.txt\n社員データ: /srv/nightfall/staff\n'}
    if stage == 3:
        files = {}
        departments = ['engineering', 'operations', 'finance', 'support', 'research']
        for i in range(30):
            files[f'{base}staff/{departments[i % 5]}/active/staff-{i:02d}/handover.txt'] = f'業務引き継ぎ {i:02d}\n定期点検を月曜の朝に実施。記録の保管担当へ連絡してください。\n'
        files[base + 'staff/engineering/retired/aoki/handover.txt'] = 'Project: GLASS\nAccount: aoki\n移送の痕跡は /srv/nightfall/logs/access.log に残した。\n'
        return files
    if stage == 4:
        lines = []
        for i in range(3000):
            user = 'aoki' if i % 17 == 0 else f'staff-{i % 30:02d}'
            project = 'GLASS' if i % 11 == 0 else 'CLOUD'
            action = 'backup' if i % 7 == 0 else 'read'
            status = 'FAIL' if user == 'aoki' and project == 'GLASS' else 'OK'
            lines.append(f'{i // 3600:02d}:{i // 60 % 60:02d}:{i % 60:02d} user={user} project={project} action={action} status={status} path=/srv/nightfall/internal/record-{i:04d}\n')
        lines[2478] = ACCESS_LINE
        return {base + 'logs/access.log': ''.join(lines)}
    if stage == 5:
        return {base + 'backups/glass-maintenance.tar.gz': archive({
            'maintenance/README.txt': '保管庫の接続設定は config/archive.env に保存している。\n平文でのパスワード保管は不適切な運用だ。\n',
            'maintenance/config/archive.env': 'ARCHIVE_PASSWORD=cinder-47\n',
        })}
    if stage == 6:
        hosts = ['relay-07'] * 24 + ['relay-02'] * 15 + ['relay-11'] * 12 + ['relay-04'] * 9
        random.Random(204).shuffle(hosts)
        return {base + 'vault/reports/before.txt': BEFORE, base + 'vault/reports/after.txt': AFTER, base + 'vault/net/transfer-destinations.log': '\n'.join(hosts) + '\n'}
    if stage == 8:
        return {home + 'recovery/recover.sh': RECOVER, home + 'recovery/recovery.conf': 'TARGET=relay-00\nOUTPUT=/home/contractor/recovery/output\n'}
    if stage == 9:
        # Incompressible deterministic data: removing cache is necessary.
        rng = random.Random(204)
        return {home + 'transfer-cache/README.txt': '再生成可能な *.tmp と空の old ディレクトリは削除してよい。\n', home + 'transfer-cache/part-1.tmp': rng.randbytes(1024 * 1024), home + 'transfer-cache/part-2.tmp': rng.randbytes(1024 * 1024)}
    return {}


OWNED = {
    1: ['home/contractor/README.txt', 'home/contractor/inbox'],
    2: ['home/contractor/.contact'], 3: ['srv/nightfall/staff'],
    4: ['srv/nightfall/logs'], 5: ['srv/nightfall/backups', 'home/contractor/work/backup'],
    6: ['srv/nightfall/vault/reports'], 7: ['srv/nightfall/vault/net'],
    8: ['home/contractor/recovery/recover.sh', 'home/contractor/recovery/recovery.conf', OUT + '/relay-receipt.txt', OUT + '/.keys'],
    9: ['home/contractor/staging', 'home/contractor/submission/evidence.tar.gz', 'home/contractor/transfer-cache'],
    10: ['home/contractor/staging', 'home/contractor/submission/evidence.tar.gz'],
}

# Japanese teaching material is editable independently of validators.
from pathlib import Path
STAGES = json.loads(Path(__file__).with_name('scenario.json').read_text(encoding='utf-8'))

HELP = '''mission: 現在の依頼 / mission check: 回答・成果物判定
mission hint: 次のヒント / mission hints: 見たヒント
mission status: 進捗と時間 / mission reset: 現在の課題を復元（確認あり）
mission replay N: 独立した練習環境を要求（exit後に起動、本編は維持）
vault unlock archive / vault unlock core: 非表示のパスワード入力
mission submit: 最終証拠の提出（外部送信なし）

less と man は q で終了。nano は Ctrl+O → Enterで保存、Ctrl+Xで終了。
実行中の処理は通常 Ctrl+C で中断できる。
cd は help cd、それ以外は man コマンド名 や コマンド名 --help で調べる。
削除や編集を間違えたら mission reset。ホーム全体の破損は運営へ復旧を依頼。
120分は目安。標準モードでは時間切れでも継続できる。
'''
COMPLETE = '''[提出確認]
アクセス記録       OK
改ざん前後の差分   OK
通信先の集計       OK
回収受領記録       OK
改ざん指示書       OK

案件 NF-204：証拠保全完了

[受信 / Aoki]
ありがとう。これで、書き換える前の数字も、指示した記録も残る。
もう「そんな事実はなかった」とは言わせない。

MISSION COMPLETE'''
