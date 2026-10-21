# NIGHTFALL：消去までの120分

Windows 11＋Ubuntu 24.04 LTS（WSL 2）で遊ぶUnix CLI学習ゲームです。実際のBashで探索・検索・編集・集計・証拠の梱包を行います。Dockerは使いません。

現在はゲーム本体と配布用スクリプトを実装した段階です。Linux上の自動検証は実施済みですが、**WSL実機でのビルド・配布・通しプレイは未検証で、配布用rootfsも未生成**です。参加者への配布前に[Windows確認表](docs/windows-validation.md)を実施してください。

- 参加者：[開始案内](docs/player.md)
- 運営：[ビルド・配布・復旧](docs/operator.md)
- 開発：[実装構成](docs/architecture.md)
- ゲームの全仕様：[spec.md](spec.md)（正解・ネタバレあり）

## 開発時の検証

Python 3.12以上とGNU系Unixコマンドを使います。実行時の外部Python依存はありません。

```bash
python3 -m unittest discover -s tests -v
bash -n scripts/provision.sh scripts/player-shell.sh scripts/bashrc
```

テストは一時ディレクトリに仮のホームと管理領域を作り、ホストの実際の `/home/contractor` や `/srv/nightfall` を変更しません。通信テストではローカルのUnixドメインソケットと疑似端末を使用します。ソケットが禁止されたサンドボックス内では、許可された環境で通信テストを実行してください。pytestがある場合は `python3 -m pytest tests` でも実行できます。

## 配布物

運営が `windows/build.ps1` で準備済みUbuntu環境を生成し、起動ファイルと一緒に配布します。ソースフォルダだけでは参加者用のセットアップは完了しません。

```text
配布フォルダ/
  初回セットアップ.cmd
  ゲーム開始.cmd
  運営用復旧.cmd
  NIGHTFALL.rootfs.tar
  NIGHTFALL.rootfs.tar.sha256
  START-HERE.md
  windows/
```
