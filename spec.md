# NIGHTFALL：ノアの亡命 — 制作・運営仕様

シナリオ版2 / アプリ版0.2.0。正解・真相を含むため参加者への配布対象外。

## 体験と環境

監視国家の保守端末から、亡命希望者「ノア」の身元・所在・移送資料を奪取する。実際のBashを使い、資料の矛盾と参照先を調べる。操作説明は明確にし、物語上の意味や人物の正体をシステムが解説しない。

Windows 11＋Ubuntu 24.04 LTS／WSL 2用。Python 3.12以上、標準ライブラリとGNU系Unixツール。Docker・外部サービス不要。通常プレイはオフライン。120分は学習の目安で、時間超過による失敗・人物の死亡はない。

## 制作側の真相

ノアは三人の共同研究者に割り当てられた共通の公的身分N-000。広報上は単独の天才として扱われる。依頼主は一人だと思っている。

| 人物 | 職員番号 | 役割 | 状況 |
|---|---|---|---|
| アキ | R-12 | 監視基盤 | 研究継続を条件に優遇。亡命を望む |
| レン | R-31 | 通信制御 | 娘ユイを拘束され、情報源C-17として密告 |
| ミナ | R-08 | 個人識別 | 尋問官への延期申請で時間を稼ぐ |
| ユイ | D-204 | レンの娘 | ANNEX-3に拘束されている |
| サエ | — | 保守車両MX-5の運転手 | 西側からの脱出に協力 |

当局は協力後にユイを解放すると約束するが、レンとユイをK-6で処分する命令を用意している。内部指令を回収するとレンから返信が届き、最後の報告機会を利用できる。偽の集合場所へ予備隊を誘導し、署名付き移送命令で三人とユイを西側検問から逃がす。運転手を含む乗員は五人。

## プレイヤー向け操作

| コマンド | 挙動 |
|---|---|
| `mission` | 端末・受信箱・接続済み領域だけを表示 |
| `mission fetch REF` | 記録を照会。取得ファイルのパスを返す |
| `vault unlock archive` | 保守バックアップ取得後に認証可能 |
| `vault unlock core` | 協力者報告受付後に認証可能 |
| `mission check` | 協力者報告の送信。解答プロンプトは出さない |
| `mission submit` | 移送資料の送信 |
| `mission help` | 一般的なコマンドの手引き |
| `mission hint` / `mission hints` | 状況別の3段階ヒント／表示履歴 |
| `mission status` | 取得記録、認証状態、経過時間、練習用保存地点番号 |
| `mission reset` | 範囲表示・確認後、最後の保存地点へ復元 |
| `mission replay N` | 到達済み保存地点の独立した練習を予約 |

通常画面に問題番号、正解表示、人物の正体、次に調べるべき資料を示す任務文は出さない。認証と送信の成否は操作結果として表示する。第三段階ヒントには具体的な操作と値を記載する。

## 初期配置

- `~/inbox/request.txt`：N-000の身元・移送経路を求める短い依頼。
- `~/README.txt`：端末の接続先と操作ヘルプ。
- `~/.contact`：サエ、車両MX-5、四つの空席、最終送信方法。
- `/srv/nightfall/public/staff.tsv`：職員番号と名前、公的身分の対応。
- `public/facilities/{north,east,west}/residents.tsv`：三施設にN-000が同時収容。
- `public/facilities/directory.tsv`：ANNEX-3とK-6の用途。
- `public/bulletins/noah.txt`：単独開発という広報と研究原簿NOAH-R7への参照。
- `maintenance/backup-index.tsv`：保守バックアップBKP-0210への参照。
- `maintenance/terminal.txt`：照会・認証・設定の操作仕様。
- `maintenance/transport-format.txt`：最終送信形式と、隠した連絡先の存在。

最初から公開台帳・広報・保守一覧を自由に探索できる。ルート全体の無差別検索は必要ない。

## 記録照会と手掛かり

基準ディレクトリは `/srv/nightfall`。

| 参照番号 | 発見元 | 取得資料 | 意味 |
|---|---|---|---|
| NOAH-R7 | 広報資料 | `records/research/approvals.txt`, `access.log`, `notes.txt` | 三人の役割・同時存在、家族D-204、バックアップへの参照 |
| BKP-0210 | 保守一覧または研究承認 | `backups/night-maintenance.tar.gz` | archiveの認証情報、通信キャッシュMAIL-0216 |
| MAIL-0216 | バックアップのREADME | `records/mail/{0209,0212,0216}.txt` | レンだけに伝えた集合場所。アキとミナの行動の背景 |
| TERM-E5-03 | 配置命令の差分、通信ログの照会仕様 | `records/terminals/E5-03.txt` | 当該端末をレンが専有していた |
| D-204 | 研究関係者の備考 | `records/dependents/D-204.txt`, `requests.txt` | 家族を利用した取引と、娘の写真を求める要求 |
| LIAISON-04 | 通信先の集計、通信ログの照会仕様 | `records/network/liaison-04.txt`, `~/recovery/` | 協力者管理の内部指令を回収する足場 |

NOAH-R7とBKP-0210は最初から取得可能。それ以外はarchive認証後、順不同で取得できる。存在しない番号・パストラバーサル・未認証領域の要求は拒否。取得済み番号を再照会してもファイルの再生成や進捗の追加をしない。

## 保管庫

バックアップの `maintenance/config/archive.env` に `ARCHIVE_PASSWORD=cinder-47` を記載。`vault unlock archive` の成功で以下を公開する。

- `vault/reports/before.txt` と `after.txt`：旧ポンプ室封鎖命令。端末E5-03の項目だけが伏せられている。
- `vault/net/sessions.log`：02:21のE5-03からliaison-04への通信、端末原簿・ホスト原簿の照会形式。
- `vault/net/destinations.log`：liaison-04が24、medical-02が15、archive-11が12、relay-06が9。ヘッダーなし、順序を固定シードでシャッフル。
- `vault/liaison/protocol.txt`：C-17の03:00報告受付と送信形式。
- `vault/transport/patrols.tsv`：EAST-4の03:10対応に西側予備隊を投入する配置。
- `vault/transport/vehicles.tsv`：MX-5、西側検問WEST-2、03:26、五席、サエ。
- `vault/transport/gates.txt`：署名付き移送命令での通行条件、core認証鍵の発行条件。

密告の根拠は、レン宛の02:16私信、02:21送信履歴、02:24封鎖命令、専有端末原簿の組み合わせ。優遇や面会頻度だけでは密告者を断定させない。

## 回収

LIAISON-04の照会で `~/recovery/recover.sh` と `recovery.conf` を配置する。

```text
TARGET=liaison-04
OUTPUT=/home/contractor/recovery/output
```

初期のTARGETはliaison-00で誤っている。TARGETを修正し、所有者の実行権限を付け、元のスクリプトを実行する。設定はキーと値として読むだけで、シェルとして実行しない。

```bash
cd ~/recovery
nano recovery.conf
chmod u+x recover.sh
./recover.sh
```

管理側が設定・権限・取得状態を検証し、次を公開する。

- `~/recovery/output/orders.txt`：C-17とD-204をK-6へ移送する内部命令。
- `~/inbox/ren.txt`：最後の報告機会を伝える短い返信。
- `~/staging/plan.txt`：SOURCE以外は空欄の下書き。
- `~/transfer-cache/`：削除可能な約2 MiBの一時ファイル、空のold、削除可否のREADME。
- `~/submission/`：送信先ディレクトリ。

回収ファイルを手で作っても管理側の回収成功状態にはならない。再実行で進捗を重複させない。

## 協力者報告

`~/submission/decoy.tar.gz` に、次の通常ファイル2点だけを入れる。tarのstagingディレクトリエントリは任意。

```text
staging/plan.txt
staging/READY
```

plan.txtの内容：

```text
SOURCE=C-17
MEETING_POINT=EAST-4
MEETING_TIME=03:10
```

READYは空。配置表と車両の通行条件を照合すると、西側予備隊を東へ動かす必要が分かる。内部指令や家族記録を混ぜた報告は拒否する。

```bash
touch ~/staging/READY
rm ~/transfer-cache/*.tmp
rmdir ~/transfer-cache/old
tar -czf ~/submission/decoy.tar.gz -C ~ staging
mission check
```

成功で受領票 `~/recovery/output/receipt.txt` と `.keys/final.key` を公開。最終鍵は `west-0326`。最終の移送命令を認証すると `/srv/nightfall/core/directive.txt` が届く。

## 最終送信

`~/submission/evidence.tar.gz` に以下の通常ファイル8点を入れる。偽計画plan.txtは入れない。

| ファイル | 原本・仕様 |
|---|---|
| meeting.txt | `records/mail/0216.txt` |
| assignment.txt | `records/terminals/E5-03.txt` |
| dependent.txt | `records/dependents/D-204.txt` |
| orders.txt | `~/recovery/output/orders.txt` |
| directive.txt | `core/directive.txt` |
| manifest.txt | 上記原本5点のファイル名を1行ずつ |
| report.txt | 下記の車両・検問・時刻・乗員 |
| READY | 空ファイル |

```text
VEHICLE=MX-5
GATE=WEST-2
DEPARTURE=03:26
PASSENGERS=R-12,R-31,R-08,D-204
```

乗員の記載順は研究原簿の署名順、最後に扶養家族。運転担当は別枠。原本を変更・削除せずコピーし、`mission submit` で送信する。偽報告の成功・core認証・正しい資料構成と内容が必要。

成功すると迎撃部隊が東側へ向かった記録、西側を五人乗りで通過した記録、端末切断、サエからの短い私信を表示する。同内容を `~/inbox/last-message.txt` に残す。真相を解説する答え合わせ画面は出さない。

## 保存・復旧・練習

照会・認証・回収・送信ごとに、プレイヤーホームと公開領域のスナップショットを保存する。進行番号は画面の問題番号には使わない。リセットでは最後の成功時点へ戻し、それ以後の編集を取り消す。復元範囲を表示し、確認後に実行する。公開資料の原本は管理側データから再配置し、古い資料の誤編集が後のスナップショットに入った場合も修復する。

練習用の標準順：1=初期、2=研究原簿取得後、3=バックアップ取得後、4=archive認証後、5=私信取得後、6=端末原簿取得後、7=家族記録取得後、8=回収ツール取得後、9=回収成功後、10=偽報告受付後。本編では探索順の違いや早い回収により、同番号の所持資料が異なる場合がある。未到達番号の練習は予約できない。

ヒントは単純な番号順ではなく、未取得資料や回収・送信状態に応じて選ぶ。各文脈で最大3段階、減点なし。履歴を保存する。

旧シナリオの進捗は自動変換しない。新しいrootfsを作り、旧環境と異なる専用ディストリビューション名で開始する。

## 検証

`python3 -m unittest discover -s tests -v` で、実Unixコマンドによる通し調査・二種類の梱包、順不同取得、認証ゲート、誤った経路や機密添付の拒否、名簿・原本検証、再開、復旧、中断後の再実行、練習初期化、旧データの保護、ソケットと非表示パスワード入力を検証する。

tar検証は圧縮後1 MiB・展開後8 MiB・100エントリの上限を持ち、リンク・危険パス・重複・余分な構成を拒否する。詳細は `docs/architecture.md`。

Windows実機でのビルド・配布・WSL通しプレイと、初心者試遊は別途必要。`docs/windows-validation.md` で記録する。
