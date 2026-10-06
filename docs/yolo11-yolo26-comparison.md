# YOLO11 / YOLO26 静止画像比較

公式確認（2026-10-05）：

- [Ultralytics YOLO26モデル一覧・推論方式](https://docs.ultralytics.com/models/yolo26/)
- [Ultralytics 8.4.0のYOLO26追加リリース](https://github.com/ultralytics/ultralytics/releases/tag/v8.4.0)
- 物体検知重み：`yolo26n.pt`、`yolo26s.pt`。公式assetsのv8.4.0から準備。
- 現在のUltralytics 8.4.171で読み込み・推論できたため、既存仮想環境を更新していません。

## 実行コマンド（PowerShell）

```powershell
.\.venv\Scripts\python.exe tools\compare_image_models.py --preset yolo11-yolo26 --image IMG\demo.png --mask-config .camera-runtime\masks\demo-v1.json
```

不足モデルを準備する場合のみ `--download-models` を追加します。今回は準備済みです。
マスクなしだけの比較では `--mask-config` を省略します。
従来の3条件比較は `--preset legacy`（既定）で引き続き使えます。

まずマスクなし4条件、その後同じマスクで4条件を実行します。
全条件personのみ・confidence=0.25・imgsz=1280・CPU・max_det=300で統一。
今回はYOLO11・YOLO26とも、既定のone-to-many・NMSあり方式（IoU=0.7）で動作しました。
YOLO26にはNMSなしの方式もありますが、この比較では既定のヘッドを変更していません。
スクリプトは実際にNMSなしで動作する重みの場合にIoUを渡さず、空欄/nullとして記録します。
公式ドキュメントの現在の既定値が変わっても、実行したバックエンドの方式を確認して保存します。

## 出力・実人数の記入

`.camera-runtime/model-comparisons/日時-識別子/` に毎回新しく保存し、既存結果を上書きしません。
`overview.png` は上段マスクなし、下段マスクあり。左からYOLO11n、YOLO11s、YOLO26n、YOLO26s。
各条件の元解像度PNGと、各モデルの前後比較PNGも保存します。
`review.csv` には実人数・見逃し・誤検知・notesの空欄があります。利用者が目視で記入してください。
マスクありでは残った検知対象領域の実人数を記入し、境界上の人物の扱いをnotesに記録します。
実人数を自動で推定しません。マスク後に件数が増えた場合も、正しい追加検知か誤検知かを枠で確認します。

`results.json` はモデル名・重みハッシュ、画像ハッシュ、マスク座標、ライブラリ版、実際の推論方式、
設定値、人数、枠、confidence、反復ごとの時間を保存します。
各条件・段階で1回ウォームアップ後、3回計測したpredict呼出し時間の中央値です。
前処理・推論・後処理を含み、モデルロード・ウォームアップ・画像描画・ファイル保存を除きます。
Ultralyticsの前処理・推論・後処理別の時間もJSONに保存します。
同じPCでも負荷で時間は変動します。DB保存は行いません。

今回の出力：`.camera-runtime/model-comparisons/20261005-134920-b3d8c5fd/`
