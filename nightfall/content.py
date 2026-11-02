"""Private, deterministic records for NIGHTFALL: ノアの亡命."""
import gzip
import io
import json
from pathlib import Path
import random
import tarfile

TITLE = 'NIGHTFALL：ノアの亡命'
SCENARIO = 2
HOME = 'home/contractor'
BASE = 'srv/nightfall'
OUT = HOME + '/recovery/output'
ROOTS = [HOME, BASE]
KEY = 'west-0326'
PASSWORD = 'cinder-47'
TARGET = 'liaison-04'
REFS = ['NOAH-R7', 'BKP-0210', 'MAIL-0216', 'TERM-E5-03', 'D-204', 'LIAISON-04']
RESTRICTED = {'MAIL-0216', 'TERM-E5-03', 'D-204', 'LIAISON-04'}
PLAN = b'SOURCE=C-17\nMEETING_POINT=EAST-4\nMEETING_TIME=03:10\n'
REPORT = b'VEHICLE=MX-5\nGATE=WEST-2\nDEPARTURE=03:26\nPASSENGERS=R-12,R-31,R-08,D-204\n'
MEETING = '02:16 FROM: サエ / TO: R-31 / PRIVATE\n03:10、旧ポンプ室。東側搬入口は使わない。\nほかの二人への連絡は待ってほしい。\n'
ASSIGNMENT = 'TERMINAL=E5-03\nASSIGNED_TO=R-31\nVALID=00:00-04:00\nMODE=EXCLUSIVE\n'
DEPENDENT = 'ID=D-204\nNAME=ユイ\nGUARDIAN=R-31\nLOCATION=ANNEX-3\nCONTACT=SUSPENDED\n04:10 保護解除予定。最終報告の受領を条件とする。\n'
ORDERS = '02:55 / LIAISON INTERNAL\n04:10 対象: C-17 / D-204\n移送先: K-6\n区分: 最終処理\n保護解除の通知は送信しない。\n'
DIRECTIVE = '03:19 / TRANSPORT UPDATE\nR-12 NORTH-2 -> WEST-2\nR-31 EAST-5 -> WEST-2\nR-08 WEST-1 -> WEST-2\nD-204 ANNEX-3 -> WEST-2\nVEHICLE=MX-5\nDEPARTURE=03:26\n認証: west-0326\n'
EVIDENCE = {'meeting.txt': MEETING.encode(), 'assignment.txt': ASSIGNMENT.encode(),
            'dependent.txt': DEPENDENT.encode(), 'orders.txt': ORDERS.encode()}
SOURCES = {'meeting.txt': BASE + '/records/mail/0216.txt',
           'assignment.txt': BASE + '/records/terminals/E5-03.txt',
           'dependent.txt': BASE + '/records/dependents/D-204.txt',
           'orders.txt': OUT + '/orders.txt'}
RECOVER = '''#!/bin/bash
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
if [ "$here" != /home/contractor/recovery ]; then
  echo '元の /home/contractor/recovery/recover.sh を起動してください。' >&2
  exit 1
fi
exec /usr/local/bin/nightfall-recover
'''


def archive(files):
    buffer = io.BytesIO()
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


def initial_files():
    return {
        HOME + '/README.txt': 'NIGHTFALL MAINTENANCE TERMINAL\nHost: maintenance-03\nUser: contractor\n受信: ~/inbox/request.txt\n公開領域: /srv/nightfall/public\n保守領域: /srv/nightfall/maintenance\n操作説明: mission help\n',
        HOME + '/inbox/request.txt': 'ノアを出国させてほしい。\n身元記録と今夜の移送経路を回収してくれ。\n\n足場は夜間保守用の端末に用意した。\n職員番号は不明。身分証番号は N-000。\n移送は04:00。以後、こちらからは連絡できない。\n',
        HOME + '/.contact': '保守車両 MX-5 / 運転担当: サエ\n車内の席は四つ空けてある。\n署名付きの移送命令と乗員名簿があれば、西側検問を通せる。\n受領: mission submit\n送信形式: /srv/nightfall/maintenance/transport-format.txt\n',
        BASE + '/public/README.txt': '施設別の収容台帳と職員台帳を公開。研究原簿・保守バックアップは参照番号で照会。\n端末操作: mission fetch 参照番号\n',
        BASE + '/public/staff.tsv': 'STAFF\tNAME\tIDENTITY\nR-12\tアキ\tN-000\nR-31\tレン\tN-000\nR-08\tミナ\tN-000\nR-04\tカイ\tN-014\n',
        BASE + '/public/facilities/north/residents.tsv': 'IDENTITY\tSTAFF\tROOM\nN-000\tR-12\tNORTH-2\nN-014\tR-04\tNORTH-6\n',
        BASE + '/public/facilities/east/residents.tsv': 'IDENTITY\tSTAFF\tROOM\nN-000\tR-31\tEAST-5\n',
        BASE + '/public/facilities/west/residents.tsv': 'IDENTITY\tSTAFF\tROOM\nN-000\tR-08\tWEST-1\n',
        BASE + '/public/facilities/directory.tsv': 'NORTH-2 研究棟\nEAST-5 通信棟\nWEST-1 識別棟\nANNEX-3 家族保護棟\nK-6 廃棄設備 / 人員の受入設備なし\n',
        BASE + '/public/bulletins/noah.txt': '研究主任ノアが単独開発した次世代保安基盤。\n研究原簿: NOAH-R7\n対外発表に個別の職員名を記載しないこと。\n',
        BASE + '/maintenance/backup-index.tsv': 'REF\tTIME\tCLASS\nBKP-0200\t02:00\tROTATED\nBKP-0210\t02:10\tNIGHT-MAINTENANCE\n',
        BASE + '/maintenance/terminal.txt': '資料照会: mission fetch 参照番号\n取得済み資料への再照会は新しい進捗を作らない。\n保管庫: vault unlock archive\n回収先は recovery.conf の TARGET、OUTPUT は変更不可。\nコマンドの操作説明: mission help\n',
        BASE + '/maintenance/transport-format.txt': '連絡先はホームの通常の一覧には出さない。\n\n受領先: ~/submission/evidence.tar.gz\n梱包基準: staging/\n必要な通常ファイル:\nmeeting.txt, assignment.txt, dependent.txt, orders.txt, directive.txt\nmanifest.txt: 上記5ファイルを1行ずつ、重複なく記載\nreport.txt: VEHICLE, GATE, DEPARTURE, PASSENGERS をこの順で1行ずつ\nPASSENGERS は原簿の署名順、最後に扶養家族。運転担当は含めない。\nREADY: 空ファイル\n通常ファイルは以上8点だけ。原本は残す。\n圧縮後1 MiB以下、展開後8 MiB以下。送信はこの端末内で完結する。\n',
    }


def record_files(ref):
    records = {
        'NOAH-R7': {
            BASE + '/records/research/approvals.txt': 'BUILD=NOAH-R7\nINFRASTRUCTURE R-12 APPROVED\nCOMMUNICATION R-31 APPROVED\nIDENTITY R-08 APPROVED\n過去版: BKP-0210\n',
            BASE + '/records/research/access.log': '01:40 NORTH-2 R-12 BIOMETRIC_OK\n01:40 EAST-5 R-31 BIOMETRIC_OK\n01:40 WEST-1 R-08 BIOMETRIC_OK\n',
            BASE + '/records/research/notes.txt': 'R-12: 継続研究を条件に個室・端末利用を許可。\nR-31: 扶養家族照会 D-204。\nR-08: 面会6回。移送延期申請を3件受理。\n',
        },
        'BKP-0210': {BASE + '/backups/night-maintenance.tar.gz': archive({
            'maintenance/config/archive.env': 'ARCHIVE_PASSWORD=cinder-47\n',
            'maintenance/README.txt': '保管庫: vault unlock archive\n通信キャッシュ参照: MAIL-0216\n差分対象: /srv/nightfall/vault/reports/before.txt と after.txt\n',
        })},
        'MAIL-0216': {
            SOURCES['meeting.txt']: MEETING,
            BASE + '/records/mail/0209.txt': '02:09 FROM R-12\nここは暖房がついている。食事も出る。\nそのかわり、昨日と同じ設計を今日も書かされている。\n',
            BASE + '/records/mail/0212.txt': '02:12 FROM R-08\nまた延期を頼んだ。今度は計測器の故障ということにした。\n次に呼ばれたら、もう話すことがない。\n',
        },
        'TERM-E5-03': {SOURCES['assignment.txt']: ASSIGNMENT},
        'D-204': {
            SOURCES['dependent.txt']: DEPENDENT,
            BASE + '/records/dependents/requests.txt': '02:06 FROM R-31\n写真は先週と同じだった。\n今日の日付が分かるものを一緒に写してほしい。\n',
        },
        'LIAISON-04': {
            HOME + '/recovery/recover.sh': RECOVER,
            HOME + '/recovery/recovery.conf': 'TARGET=liaison-00\nOUTPUT=/home/contractor/recovery/output\n',
            BASE + '/records/network/liaison-04.txt': 'HOST=liaison-04\nSERVICE=協力者管理\n内部指令の保守ミラーを取得可能。\nツール: ~/recovery/recover.sh\n設定: ~/recovery/recovery.conf\n',
        },
    }
    return records[ref]


def archive_files():
    hosts = ['liaison-04'] * 24 + ['medical-02'] * 15 + ['archive-11'] * 12 + ['relay-06'] * 9
    random.Random(204).shuffle(hosts)
    before = '02:24 配置変更\nPOINT=旧ポンプ室\nSOURCE=C-17\nTERMINAL=E5-03\n配置完了期限=03:00\n'
    return {
        BASE + '/vault/reports/before.txt': before,
        BASE + '/vault/reports/after.txt': before.replace('TERMINAL=E5-03', 'TERMINAL=REDACTED'),
        BASE + '/vault/net/destinations.log': '\n'.join(hosts) + '\n',
        BASE + '/vault/net/sessions.log': '02:12 N2-01 -> archive-11 SEND_OK\n02:21 E5-03 -> liaison-04 SEND_OK\n02:22 W1-02 -> medical-02 SEND_OK\n端末原簿の照会形式: TERM-端末番号\nホスト原簿の参照番号: ホスト名を大文字に変換\n',
        BASE + '/vault/liaison/protocol.txt': '協力者報告 / C-17\n次回受付: 03:00\n経路: mission check\n送信先: ~/submission/decoy.tar.gz\n梱包: staging/plan.txt と staging/READY（空）の2点だけ\nplan.txt: SOURCE, MEETING_POINT, MEETING_TIME の順に1行ずつ\nこの報告に内部指令・個人情報を添付しないこと。\n',
        BASE + '/vault/transport/patrols.tsv': 'POINT\tDISPATCH\tEFFECT\nEAST-4\t03:10\t西側の予備隊を全員投入\nNORTH-1\t03:10\t北側部隊で対応\nWEST-2\t03:10\t西側検問を閉鎖\n',
        BASE + '/vault/transport/vehicles.tsv': 'VEHICLE\tGATE\tTIME\tSEATS\tDRIVER\nMX-5\tWEST-2\t03:26\t5\tサエ\nMX-2\tNORTH-1\t03:05\t2\t当局職員\n',
        BASE + '/vault/transport/gates.txt': '西側検問の保守運用\n予備隊が出動中の場合、署名付き移送命令による車両通行を許可。\n現行命令は core に保管。送信受付後の受領票に一時認証鍵を発行。\n',
    }


def recovery_records():
    return {
        SOURCES['orders.txt']: ORDERS,
        HOME + '/inbox/ren.txt': 'FROM: R-31\n……見たんだな。\n\n03:00に、もう一度報告することになっている。\nあちらは、まだ私を信用している。\n報告用の下書きを置いた。\n',
    }


def recovery_files():
    return {
        **recovery_records(),
        HOME + '/staging/plan.txt': 'SOURCE=C-17\nMEETING_POINT=\nMEETING_TIME=\n',
        HOME + '/transfer-cache/README.txt': '送信済み *.tmp と空の old は削除可能。\n回線容量: キャッシュと今回の送信アーカイブの合計1 MiB以下。\n',
        HOME + '/transfer-cache/part-1.tmp': random.Random(1).randbytes(1024 * 1024),
        HOME + '/transfer-cache/part-2.tmp': random.Random(2).randbytes(1024 * 1024),
    }


def decoy_files():
    return {
        OUT + '/receipt.txt': '03:00 C-17 REPORT_ACCEPTED\n03:18 EAST-4 予備隊出動\n仮認証鍵: /home/contractor/recovery/output/.keys/final.key\n認証先: vault unlock core\n',
        OUT + '/.keys/final.key': KEY + '\n',
    }


STAGES = json.loads(Path(__file__).with_name('scenario.json').read_text(encoding='utf-8'))
HELP = '''mission: 接続先と受信箱 / mission fetch 参照番号: 記録を取得
mission check: 協力者報告の送信 / mission submit: 移送資料の送信
vault unlock archive / vault unlock core: 保管庫の認証（パスワード非表示）
mission hint: 段階式ヒント / mission hints: 表示済みヒント
mission status: 取得記録・経過時間 / mission reset: 最後の保存地点に復元（確認あり）
mission replay N: 到達済みの保存地点を独立した練習環境で開く（exit後）

操作の手引き:
pwd / ls / cd: 現在地・一覧・移動。ls -la は隠しファイルも表示。
cat / less: 読む。less と man は q で終了。
find 場所 -type f -name '名前': ファイル名検索。
grep '文字列' ファイル: 内容検索。grep -R はフォルダ内を再帰検索。
|: 出力を次のコマンドへ渡す。head / tail: 先頭・末尾。
diff -u 元 更新版: 差分表示。差分があれば終了コード1。
sort | uniq -c | sort -nr: 行ごとの出現数を多い順に表示。wc -l: 行数。
mkdir -p: フォルダ作成。cp / mv: コピー・移動。touch: 空ファイル作成。
> は上書き、>> は追記。rm / rmdir: ファイル・空ディレクトリの削除。
tar -tzf: 一覧。tar -xzf ファイル -C 展開先: 展開。
tar -czf 送信先 -C ~ staging: staging を圧縮。du -sh: 容量。
nano: 編集。Ctrl+O → Enterで保存、Ctrl+Xで終了。
ls -l: 権限確認。chmod u+x: 実行権限。./名前: 起動。
詳しくは man コマンド名。cd は help cd。通常 Ctrl+C で中断可能。

操作は端末内で完結し、外部へ送信しない。プレイ時間120分は目安。
編集・削除の復旧は mission reset。ホーム全体の破損は運営へ連絡。
'''
COMPLETE = '''03:18 東側搬入口、封鎖完了。
03:22 対象者を確認できず。周辺捜索に移行。
03:26 西側検問、保守車両MX-5通過。乗員数: 5。
03:31 E5-03 通信切断。

[受信 / サエ]
あの子は眠った。
残りの三人は、まだ話をしている。

次に連絡するときは、
それぞれの名前で。
'''
