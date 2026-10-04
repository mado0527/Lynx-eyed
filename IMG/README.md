# 静止画像での人数検知デモ

このフォルダに自分で用意した `demo.jpg` や `demo.png` を置いてください。
画像はGit管理対象外です。元画像を上書きしません。DBには保存しません。
PowerShellでリポジトリのルートから実行します。

```powershell
.\.venv\Scripts\python.exe tools\camera_preview.py --image IMG\demo.png --save-changes
```

1回だけ検知し、人数・検知枠を表示します。キー入力で終了します。
結果は `.camera-runtime/captures/` に保存します。
PiやMySQLへの接続は不要です。YOLOモデルと既存仮想環境を使います。

同じ画像でマスキング範囲を選択する場合：

```powershell
.\.venv\Scripts\python.exe tools\camera_preview.py --image IMG\demo.png --select-mask .camera-runtime\masks\demo-v1.json
```

ドラッグ→Enter/Spaceで領域確定、Escで選択終了、確認画面でSを押すと保存します。
既存設定を変更するときは別名を指定します。

マスキング前後を比較する場合：

```powershell
.\.venv\Scripts\python.exe tools\camera_preview.py --image IMG\demo.png --mask-config .camera-runtime\masks\demo-v1.json --compare-mask
```

左右の比較画像とJSON、元フレームを `.camera-runtime/captures/` に保存します。
画面なしで保存する場合は `--headless` を追加します。
画像解像度とマスク設定の解像度は一致させてください。
静止画像での確認結果は、実配信での精度検証や複数カメラの重複防止とは別に扱います。
