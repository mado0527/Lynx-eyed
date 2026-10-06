# Windowsでのカメラ取得・人数検知（DB保存なし）

このページはプレビュー・画像比較の手順です。後から追加した、明示的に有効化するDB保存の手順と223教室の接続検証結果は [camera-recording.md](camera-recording.md) を参照してください。

Raspberry Piのmjpg-streamerのMJPEG配信をOpenCVで読み、YOLO11nの`person`（class 0）だけを数えます。
マスキング範囲は未確定のため、この段階ではマスキングしません。
このスクリプトはDjango・モデル・.envを読み込まず、DB保存と動画の保存を行いません。
`--save-changes`を指定した場合のみ、人数変化の確認用画像をローカル保存します。

## 準備

VS CodeのPowerShellターミナルでリポジトリのルートから実行します。

```powershell
.venv/Scripts/python.exe -m pip install -r requirements-camera.txt --index-url https://pypi.org/simple
```

モデルはUltralytics公式リリースの`yolo11n.pt`を使用します。
公式資料：https://docs.ultralytics.com/models/yolo11/

```powershell
New-Item -ItemType Directory -Force .camera-runtime/models | Out-Null
Invoke-WebRequest -Uri 'https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo11n.pt' -OutFile '.camera-runtime/models/yolo11n.pt'
```

モデル・Ultralyticsのローカル設定はGit管理対象外の`.camera-runtime`に置きます。

## 1. 映像取得だけを確認

```powershell
.venv/Scripts/python.exe tools/camera_preview.py --capture-only --headless --max-frames 3
```

`Frame acquired`が表示されたら読み込み成功です。映像のローカルプレビューは次で開けます。

```powershell
.venv/Scripts/python.exe tools/camera_preview.py --capture-only
```

入力元の既定値は`http://192.168.0.151:8080/?action=stream`です。
変更する場合は`--source 'http://.../?action=stream'`を指定します。
Windows PCとPiが同じネットワークにあること、PiのIP・ポート・配信起動状態を確認してください。
ブラウザーで動いてもPythonから到達できなければ、端末やネットワーク、Pythonのファイアウォール設定の違いを確認します。防御設定を一括解除しないでください。

## 2. 人数・検知枠のプレビュー

```powershell
.venv/Scripts/python.exe tools/camera_preview.py
```

枠にはpersonと信頼度、画面上部には`Persons: N`を表示します。
既定はCPU、信頼度閾値0.25、入力サイズ640です。例：

```powershell
.venv/Scripts/python.exe tools/camera_preview.py --conf 0.4 --imgsz 640
```

実際に映っている人数を目視して検知人数と比較してください。0人・1人・複数人、重なりや画面端での漏れ・誤検知を確認します。
YOLOの人数は検知枠数です。実人数との一致は映像で検証する必要があります。
同一人物の追跡や累計人数ではなく、そのフレームの検知人数です。

## 停止

プレビュー上で **Q** または **Esc**、ウィンドウを閉じる、またはターミナルで **Ctrl+C**。
取得失敗・推論失敗時はエラーをターミナルへ出して停止します。失敗を0人として扱いません。
開く/読む処理のタイムアウトは既定8秒で、`--timeout`で変更できます。

Webサーバーとは独立したプロセスです。今回は保存しないためトップ画面のDB記録も更新しません。
5分間隔保存、マスキング座標、場所との紐づけ、保存→トップ表示の検証は次の段階です。

## このセッションの確認結果（2026-10-02）

- 既存Windows `.venv` にOpenCV 5.0.0、Ultralytics 8.4.171と必要な依存関係を追加。既存Django依存関係の整合性チェックは正常。
- 公式YOLO11nモデルを取得し、CPUでpersonだけの推論が動くことを空のテスト画像で確認。これはPiの映像や検知精度の確認ではありません。
- 入力の接続失敗・取得失敗・person限定推論と保存無効のテスト3件が成功。
- 初回のTCP・OpenCV接続はタイムアウトしましたが、再試行で指定Piの640×480フレームを3枚取得できました。
- 実映像の5フレームをYOLO11nでperson限定推論し、取得・推論が正常終了することを確認しました。続いて人数・枠を表示するローカルプレビューを起動しました。
- 検知ログに5人・7人などの結果が出ていますが、これはモデルの検知値です。実際に映っている人数との一致や、枠の漏れ・誤検知は利用者の目視確認待ちです。精度確認済みとは扱いません。
- DB保存は未実行。画面の「自動検知：未実装」はこの段階では維持します。

## 人数変化時の画像保存

```powershell
.venv/Scripts/python.exe tools/camera_preview.py --save-changes --max-images 20 --conf 0.25 --iou 0.7
```

比較の基準になる最初の1枚と、前フレームから人数が変わった時の画像を保存します。
保存先は`.camera-runtime/captures/日時-識別子/`。1起動につき最大20枚の検知枠付きJPGで、上限到達後は保存だけを停止してプレビューを続けます。
再起動は新しいフォルダを作るため、既存画像を上書き・削除しません。全起動分の合計上限ではありません。
各画像に同じ名前のJSON（人数・時刻・設定・枠座標・confidence）とNPZ（比較用の元フレーム）が付属します。
画像はGit管理対象外です。連続動画やDBへの記録は行いません。
失敗時は0人の画像を作りません。正常な推論で0人になった場合は有効な人数変化として保存します。

### 同じ元画像で設定を比較

```powershell
.venv/Scripts/python.exe tools/compare_detections.py .camera-runtime/captures/20261002-152551-5a18d740 --max-images 6 --conf 0.35 --iou 0.5
```

保存フォルダを指定すると、各元画像について「保存時の設定」「confidenceのみ変更」「IoUのみ変更」の3段比較画像を作ります。
比較画像の上限はこのコマンド1回につき6枚。基準画像は変更しません。プレビューの既定設定も変更しません。
総人数が6に近づいたかだけでなく、元から正しく検知していた各人物の枠が残ったかを確認してください。

### 今回の比較結果

現在設定はconfidence=0.25、NMS IoU=0.70（インストール済みUltralyticsの既定値も0.70）。
6→7の保存画像では黒い服の人物付近に複数の重なった枠があり、重複検知候補が見られます。
この画像においては、離れた椅子やカバンへの余分な枠は確認されません。全フレームで物への誤検知がないとは断定しません。

| 元画像 | 現在0.25 / 0.70 | confidenceのみ0.35 | IoUのみ0.50 |
|---|---:|---:|---:|
| 001（初回） | 6 | 4 | 4 |
| 002（6→7） | 7 | 5 | 4 |
| 003（7→6） | 6 | 5 | 4 |
| 004（6→7） | 7 | 3 | 4 |
| 005（7→6） | 6 | 3 | 4 |
| 006（6→7） | 7 | 3 | 4 |

confidenceを0.35にすると、右端の白い服の実人物の枠が消える例があります。
IoUを0.50にすると枠は減りますが、密集した別人物まで除去した可能性を排除できません。
そのため0.35 / 0.50は既定設定へ採用していません。保存時点でも全員が映っているか、重複と未検知が同時に起きていないか、現地の目視と比較してください。
保存上限・人数変化・取得失敗・person限定のテスト4件は成功しています。
