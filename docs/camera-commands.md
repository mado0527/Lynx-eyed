# 教室232：カメラ起動コマンド（Windows PowerShell）

現在の配信URL：`http://192.168.0.151:8080/?action=stream`

プロジェクトのフォルダーから実行します。PCからカメラへ接続できるネットワークを使用してください。

```powershell
cd C:\Users\user\Documents\GitHub\Lynx-eyed
```

`.venv` が有効でも無効でも、以下のPython指定で実行できます。
**通常運用は「2. マスク付きでDB保存する」です。** マスクが作成済みなら、毎回作り直す必要はありません。
同じカメラの処理を重ねて起動せず、切り替えるときは先に実行中の処理を停止してください。

## 1. 初回のみ：マスクを作成する

`232-v1.json` がまだない場合に実行します。この操作は範囲の設定だけで、DBには保存しません。

```powershell
.\.venv\Scripts\python.exe tools\camera_preview.py --source "http://192.168.0.151:8080/?action=stream" --timeout 30 --select-mask .camera-runtime\masks\232-v1.json
```

1. 検知から除外する領域をマウスでドラッグします。人を検知したい範囲は隠さないでください。
2. **Enter / Space** で領域を確定します。必要なら別の領域を追加します。
3. **Esc** で領域選択を終えます。
4. 黒塗りされた確認ウィンドウをクリックし、**S** を押して保存します。
5. `Mask configuration saved` が出れば作成完了です。Ctrl+Cや確認画面のEsc / Qは保存せず終了します。

設定の存在確認：

```powershell
Test-Path .camera-runtime\masks\232-v1.json
```

`True` ならファイルがあります。`Mask file already exists` は既存設定の上書きを防ぐための表示です。
範囲を変更する場合は `--select-mask .camera-runtime\masks\232-v2.json` など新しい名前で作成し、以降の `--mask-config` も同じ名前に変更します。
**カメラの向きや解像度が変わった場合も、範囲を設定し直してください。**

### 保存済みの黒塗り範囲だけを消す

実行中のカメラを **Ctrl+C** で停止し、PowerShellで次を実行します。
`$path` には、現在 `--mask-config` で指定しているファイルを設定してください。

```powershell
$path = '.camera-runtime\masks\232-v1.json'
$mask = Get-Content -LiteralPath $path -Raw -Encoding utf8 | ConvertFrom-Json
$mask.rectangles = @()
$mask | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $path -Encoding utf8
```

保存済みの黒塗り範囲をすべて消し、同じファイルへ上書きします。解像度設定とDBデータは変更しません。
このリセット操作は、毎回同じファイルへ上書きして使えます。設定を残したい場合は、先にファイルをコピーしておいてください。
その後、同じ `--mask-config` の起動コマンドでカメラを起動し直すと、黒塗り範囲がない状態で動作します。

### 黒塗り範囲を選び直す

`--select-mask` は既存ファイルへ上書きできません。範囲をリセットしてもファイル自体は残るため、新しい名前で作成します。

```powershell
.\.venv\Scripts\python.exe tools\camera_preview.py --source "http://192.168.0.151:8080/?action=stream" --timeout 30 --select-mask .camera-runtime\masks\232-v2.json
```

範囲を選択して **S** で保存したら、通常運用の起動コマンドも新しいファイル名に変更します。
以下は教室232の場所IDが1の場合です。

```powershell
.\.venv\Scripts\python.exe tools\camera_preview.py --source "http://192.168.0.151:8080/?action=stream" --timeout 30 --mask-config .camera-runtime\masks\232-v2.json --save-db --location-id 1
```

すでに `232-v2.json` がある場合は、`232-v3.json` など未使用の名前にしてください。

## 2. 通常運用：マスク付きでDB保存する

教室232の場所IDが **1の場合**のコマンドです。教室名232と場所IDは別です。
PCや接続先DBが変わったときは、先に場所IDを確認してください。

```powershell
.\.venv\Scripts\python.exe manage.py shell -c "from crowd_app.models import LocationMaster; print(list(LocationMaster.objects.values('location_id', 'name', 'capacity')))"
```

人数検知・マスク付きプレビュー・DB保存を起動：

```powershell
.\.venv\Scripts\python.exe tools\camera_preview.py --source "http://192.168.0.151:8080/?action=stream" --timeout 30 --mask-config .camera-runtime\masks\232-v1.json --save-db --location-id 1
```

- 起動後、最初の正常な推論結果を保存します。以降は保存完了から300秒（5分）後以降に再計測・保存します。
- `DB saved: ... people=9 ...` などが出れば保存成功です。正常に検知した0人も保存します。
- `Waiting for next measurement` は次の計測待ちです。表示の人数は前回の結果で、待機中は検知枠・人数を更新しません。映像にはマスクを適用します。
- 保存先は既存の `.env` とプロセスの環境変数に従います。このコマンドは混雑記録を追加し、混雑予測は生成しません。

映像ウィンドウなしで運用する場合は、同じコマンドの末尾に `--headless` を付けます。

## 3. 検知確認用：DB保存なしで連続検知する

人数が正しく検知されるか、マスクが人を隠していないかを確認するときだけ使います。
通常運用と同じマスクを使いますが、`--save-db` を付けないためDBへ記録しません。

```powershell
.\.venv\Scripts\python.exe tools\camera_preview.py --source "http://192.168.0.151:8080/?action=stream" --timeout 30 --mask-config .camera-runtime\masks\232-v1.json
```

こちらは5分待機せず、各フレームで人数検知します。確認後は停止し、「2」のDB保存コマンドへ戻してください。

## 4. 接続確認用：映像取得だけを試す

マスク・人数検知・DB保存を使わず、カメラへ接続できるかを確認します。

```powershell
.\.venv\Scripts\python.exe tools\camera_preview.py --source "http://192.168.0.151:8080/?action=stream" --timeout 30 --capture-only
```

`Frame acquired: 1280x720` などが表示されれば取得成功です。

## 5. マスク前後を同じフレームで比較する

マスクによる検知への影響を調べるためのコマンドです。比較画像などをローカルへ保存して終了し、DBには保存しません。

```powershell
.\.venv\Scripts\python.exe tools\camera_preview.py --source "http://192.168.0.151:8080/?action=stream" --timeout 30 --mask-config .camera-runtime\masks\232-v1.json --compare-mask --headless --max-frames 1 --max-images 1
```

保存先は実行ログで確認できます。`--compare-mask` / `--select-mask` と `--save-db` は併用できません。

## 停止方法

実行中のPowerShellで **Ctrl+C** を押します。映像ウィンドウでは **Q / Esc**、またはウィンドウを閉じても停止します。
停止しても保存済みDBデータは削除されません。

## エラー・ログの見方

### うまくいかない場合

カメラへの接続・映像取得やDB通信が失敗した場合は、ターミナルに「エラーが発生しました」と表示して停止します。通信失敗を0人として保存しません。
Web画面も、DBとの通信失敗時には同じ文言を表示します。開いている画面でPCのネットワーク切断を検出した場合も同じ文言を表示し、再接続すると切断の表示を消します。
ページを開く前にWebサーバーへ接続できない場合は、ブラウザ自身のエラー画面になります。

| 表示 | 意味・対処 |
| --- | --- |
| `Mask file not found` | 指定した設定がありません。「1」で作成・保存し、パスを確認 |
| `Mask file already exists` | 作成済みです。通常起動には `--select-mask` ではなく `--mask-config` を使用 |
| `Mask configuration cancelled` | 設定は保存されていません。確認画面でSを押して保存 |
| `Input open failed` / `Stream timeout` | 配信の起動、IP・ポート、ネットワーク、映像URLを確認 |
| `Exclusion rectangles=0` | 除外領域が0個。必要ならマスク範囲を再設定 |
| `DB writes disabled` | DB保存なしの確認モード |
| `DB saved` | DB保存成功 |
| `Model is missing` | `.camera-runtime\models\yolo11n.pt` を確認 |

接続待ち時間は `--timeout 30` で30秒に指定しています。映像URLにはHTMLの閲覧ページではなく、ストリームを直接返すURLを指定します。
DB保存時のログは `.camera-runtime\logs\recording-*.log` に出力されます。

## 詳細手順

- [映像取得・人数検知](camera-preview.md)
- [DB保存](camera-recording.md)
- [マスキング](camera-masking.md)
