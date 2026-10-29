# カメラ起動コマンド一覧（Windows PowerShell）

VS Codeでプロジェクトのフォルダーを開き、PowerShellから実行します。
以下は現在の配信URL `http://192.168.0.151:8080/?action=stream` を使用する例です。
PCからカメラへ接続できるネットワークで実行してください。

```powershell
cd C:\Users\user\Documents\GitHub\Lynx-eyed
```

`.venv` の有効化は省略できます。以下では仮想環境のPythonを直接指定しています。
接続待ちは `--timeout 30` で30秒に設定しています。

## 1. 映像だけ確認する（DB保存なし）

```powershell
.\.venv\Scripts\python.exe tools\camera_preview.py --source "http://192.168.0.151:8080/?action=stream" --timeout 30 --capture-only
```

`Frame acquired: 1280x720` などが表示されれば映像取得成功です。人数検知は行いません。

## 2. 映像と人数検知を表示する（DB保存なし）

```powershell
.\.venv\Scripts\python.exe tools\camera_preview.py --source "http://192.168.0.151:8080/?action=stream" --timeout 30
```

## 3. 人数検知してDBに保存する

まず場所IDを確認します。場所名「223」と場所IDは別です。PCや接続先DBによってIDが異なる場合があります。

```powershell
.\.venv\Scripts\python.exe manage.py shell -c "from crowd_app.models import LocationMaster; print(list(LocationMaster.objects.values('location_id', 'name', 'capacity')))"
```

以下は場所223の `location_id` が **1の場合**です。違う場合は `--location-id 1` の数字を置き換えてください。

```powershell
.\.venv\Scripts\python.exe tools\camera_preview.py --source "http://192.168.0.151:8080/?action=stream" --timeout 30 --save-db --location-id 1
```

最初の正常な推論を保存し、その後は保存完了から300秒（5分）後以降に次の計測・保存を行います。
`DB saved` が保存成功の目印です。保存先は既存の `.env` とプロセスの環境変数に従います。

映像ウィンドウを表示せず、人数検知と保存を行う場合：

```powershell
.\.venv\Scripts\python.exe tools\camera_preview.py --source "http://192.168.0.151:8080/?action=stream" --timeout 30 --save-db --location-id 1 --headless
```

短い間隔で2件だけ保存して終了する場合（実DBに追加されます）：

```powershell
.\.venv\Scripts\python.exe tools\camera_preview.py --source "http://192.168.0.151:8080/?action=stream" --timeout 30 --save-db --location-id 1 --interval 5 --max-records 2 --headless
```

## 4. マスクの除外領域を作成する（DB保存なし）

新しい設定ファイルを作成します。既存ファイルを上書きせず、必要に応じて名前を変更してください。

```powershell
.\.venv\Scripts\python.exe tools\camera_preview.py --source "http://192.168.0.151:8080/?action=stream" --timeout 30 --select-mask .camera-runtime\masks\223-v1.json
```

矩形選択・保存操作の詳細は [camera-masking.md](camera-masking.md) を参照してください。

## 5. 保存済みマスクを使って人数検知する（DB保存なし）

指定したマスク設定ファイルが存在することを確認してください。

```powershell
.\.venv\Scripts\python.exe tools\camera_preview.py --source "http://192.168.0.151:8080/?action=stream" --timeout 30 --mask-config .camera-runtime\masks\223-v1.json
```

## 6. マスク前後を1フレーム比較して保存する（DB保存なし）

```powershell
.\.venv\Scripts\python.exe tools\camera_preview.py --source "http://192.168.0.151:8080/?action=stream" --timeout 30 --mask-config .camera-runtime\masks\223-v1.json --compare-mask --headless --max-frames 1 --max-images 1
```

比較画像などをローカルへ保存して自動終了します。保存先は実行ログで確認できます。
`--compare-mask` と `--save-db` は併用できません。

## 7. マスクを使ってDB保存する

```powershell
.\.venv\Scripts\python.exe tools\camera_preview.py --source "http://192.168.0.151:8080/?action=stream" --timeout 30 --mask-config .camera-runtime\masks\223-v1.json --save-db --location-id 1
```

場所IDとマスク設定ファイルは事前に確認してください。

## 停止方法

実行中のPowerShellで **Ctrl+C** を押します。映像ウィンドウがある場合は **Q / Esc** でも停止できます。
停止しても保存済みのDBデータは削除されません。

## よくあるログ

| 表示 | 意味・確認すること |
| --- | --- |
| `DB writes disabled` | DB保存なし。保存する場合は `--save-db --location-id ...` を指定 |
| `Frame acquired` | 映像取得成功 |
| `Exclusion rectangles=0` | 適用する除外領域が0個。マスク使用時は設定内容を確認 |
| `DB saved` | DB保存成功 |
| `Input open failed` / `Stream timeout` | カメラの起動、IP・ポート、ネットワーク、映像URLを確認 |
| `Model is missing` | `.camera-runtime\models\yolo11n.pt` を確認 |

配信URLは映像ストリームを直接返すURLを指定します。閲覧用HTMLページでは取得できません。
人数検知にはカメラ用の依存関係とモデルが必要です。

## 詳細手順

- [映像取得・人数検知](camera-preview.md)
- [DB保存](camera-recording.md)
- [マスキング](camera-masking.md)
