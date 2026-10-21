# 運営用：ビルド・配布・復旧

このページとソースの `spec.md` は正解データの場所を含むため、参加者用の開始案内とは分けて扱います。

## 前提

- ビルド用PC：Windows 11、現在のWSL 2、インターネット接続、Windows標準のPowerShell 5.1とtar。
- WSL導入時のみ管理者権限が必要です。管理者PowerShellで `wsl --install --no-distribution` を実行し、案内に従って再起動します。既にWSLがある場合は必要に応じて `wsl --update` を実行します。
- ビルド用に一時的な専用WSL環境を作成します。普段使うUbuntuでは `scripts/provision.sh` を実行しないでください。
- 配布イメージは参加者PCと同じCPUアーキテクチャで作成します。x64用とARM64用のイメージは別に配布してください。

## Ubuntu環境のビルド

1. [Ubuntu公式のWSL用24.04イメージ](https://cloud-images.ubuntu.com/wsl/releases/24.04/current/)から、対象CPUのrootfsとSHA256SUMSを入手します。公式配布元と署名済みチェックサムを確認したデータを使ってください。`.sha256`は破損検出用で、配布元の真正性を単独で保証するものではありません。
2. ソースフォルダでPowerShellを開き、実ファイルのパスと、確認したSHA256値を指定します。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\windows\build.ps1 `
  -UbuntuRootfs 'C:\Downloads\ubuntu-noble-wsl-amd64-24.04lts.rootfs.tar.gz' `
  -UbuntuSha256 '<公式SHA256SUMSで確認した64桁の値>'
```

ビルダーは固有名の `NIGHTFALL-BUILD-...` を作り、Ubuntuパッケージ、マニュアル、ゲーム管理と一般ユーザーを導入し、`dist`へエクスポートします。通常は最後にそのビルド用環境だけを削除します。調査用に残す場合は `-KeepBuildEnvironment` を指定してください。既存の配布イメージを上書きしません。再ビルドは `-OutputDirectory` で新しい出力先を指定します。

ビルドにはネット接続が必要です。配布済み環境の通常プレイはオフラインで行えます。Ubuntuの版・導入パッケージ一覧はイメージ内の `/opt/nightfall/packages.txt` に記録します。同一の配布環境を再現する場合は、検証済みrootfsとそのチェックサムを保管してください。再ビルド時のaptパッケージは更新されるため、毎回バイト単位で同じrootfsになることは保証していません。

## 配布と初回セットアップ

`dist`全体を配布し、参加者に `初回セットアップ.cmd` → `ゲーム開始.cmd` を実行してもらいます。ソースのゲーム仕様書を配布する必要はありません。

専用ディストリビューション名は `NIGHTFALL`、格納先は `%LOCALAPPDATA%\NIGHTFALL\distros\NIGHTFALL` です。既存の同名環境がNIGHTFALLなら再利用し、進捗を保持します。それ以外の環境は変更しません。別名を使う場合は、セットアップと起動の両方に同じ `-Name` を渡します。

```powershell
.\初回セットアップ.cmd -Name NIGHTFALL-club
.\ゲーム開始.cmd -Name NIGHTFALL-club
```

イメージ不在・ハッシュ不一致・WSL未導入は説明を表示して停止します。インポート途中の失敗で環境や格納先が残った場合は、別名を選ぶか、運営が対象を確認して不要な専用環境だけを片付けてください。ユーザーの既存環境は自動削除しません。

## 復旧

通常はゲーム内の `mission reset` を使います。復元対象が表示され、`yes`を入力した場合だけ復元します。

ホーム全体などの破損は、ゲームを終了してから `運営用復旧.cmd` を実行します。確認欄に `RESTORE` を入力すると、その専用環境の `/home/contractor` と `/srv/nightfall` を現在ステージ開始時のスナップショットへ戻します。現在ステージ中の編集は失われます。過去のクリア記録とヒント履歴は維持します。S10ではcore解放も維持します。

管理サービスの状態・ログは運営がWindows PowerShellから確認できます。

```powershell
wsl -d NIGHTFALL -u root -- systemctl status nightfall.service
wsl -d NIGHTFALL -u root -- journalctl -u nightfall.service -n 50 --no-pager
```

## 練習環境

`mission replay N`は要求を管理側に保存します。参加者がシェルを `exit` で抜けた後、Windowsの起動処理が配布rootfsから `NIGHTFALL-practice-SN-...` を新規作成します。練習から `exit` すると本編へ戻ります。練習には元の配布rootfsも必要です。作成には空き容量と時間が必要で、開始済みの練習環境は保存されます。

不要な練習環境は、運営が `wsl --list --verbose` で名前を確認してから、その練習環境だけを `wsl --unregister <練習環境名>` で削除できます。この操作は対象の進捗・ファイルを完全に削除します。本編や個人用Ubuntuには実行しないでください。

## 分離の範囲

ゲーム内は非rootのcontractorユーザーを使用します。Windowsドライブの自動マウントとWindows実行ファイルの起動を専用環境内で無効にします。Windows全体の `.wslconfig` は変更しません。

管理サービスは、所有権の設定と課題の復元のため、専用WSL内のrootで実行します。systemdで書き込み先と利用可能なcapabilityを制限し、プレイヤーの操作は固定のAPIだけで受け付けます。判定原本・SQLite・スナップショット・管理コードはroot専用です。Windows側の所有者がrootでWSLに入ることを防ぐ設計ではありません。また、オフラインで遊べる構成ですが、WSL環境そのもののネットワークを遮断する設定は行いません。
