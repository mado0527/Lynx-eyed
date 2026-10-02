# Windowsでのカメラ取得・人数検知（DB保存なし）

Raspberry Piのmjpg-streamerのMJPEG配信をOpenCVで読み、YOLO11nの`person`（class 0）だけを数えます。
マスキング範囲は未確定のため、この段階ではマスキングしません。
このスクリプトはDjango・モデル・.envを読み込まず、DB保存と画像・動画の保存を行いません。

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

入力元の既定値は`http://192.168.0.134:8080/?action=stream`です。
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
