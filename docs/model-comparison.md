# 密集した集合写真のモデル比較（Windows・DB保存なし）

`tools/compare_image_models.py` は既存 `ImageInput` とマスク読込み・黒塗り・前後比較画像作成を再利用します。
Djangoの保存処理は呼ばず、DB保存オプションもありません。画像・マスク・既存記録を変更しません。

## 起動

既存仮想環境で実行します。YOLO11n/640 → YOLO11n/1280 → YOLO11s/1280の順です。

マスクなしだけを先に確認する場合：

```powershell
.\.venv\Scripts\python.exe tools\compare_image_models.py --image IMG\demo.png
```

マスクなし3条件を実行した後、同じマスクで3条件を実行する場合：

```powershell
.\.venv\Scripts\python.exe tools\compare_image_models.py --image IMG\demo.png --mask-config .camera-runtime\masks\demo-v1.json
```

モデルは `.camera-runtime/models/yolo11n.pt` と `yolo11s.pt` を使います。
今回YOLO11sを公式Ultralytics assetsから準備済みです。
別の環境で不足するモデルを準備する場合は `--download-models` を追加します。
confidenceは `--conf 0.25`、NMS IoUは `--iou 0.7` が既定で、全条件共通です。
CPUで各条件・各段階1回ウォームアップ後に3回計測します（`--repeats`で変更可）。
Ctrl+Cで停止できます。途中終了では結果が一部のみになるため再実行してください。

## 保存物と実人数の記入

`.camera-runtime/model-comparisons/日時-識別子/` に各実行の結果を別々に保存します。

- `overview.png`：上段マスクなし、下段マスクあり。左から3条件。
- 各条件のPNG：元解像度の検知枠付き画像。
- `before-after_*.png`：各条件の同一フレーム前後比較。
- `results.json`：画像・モデルSHA256、元画像解像度、実際のマスク座標、ライブラリ版、
  人数、全検知枠・confidence、全反復の時間、Ultralytics内訳時間。
- `review.csv`：Excel等で `actual_count`（実人数）、`missed_people`（見逃し）、
  `false_detections`（誤検知）、`notes` を目視確認して記入する表。初期値は空欄。
- `original.png`：比較に使った元画像のコピー。

マスクありの実人数は、検知対象として残した領域の人数を記録し、元画像全体の実人数とは区別してください。
境界にまたがる人の扱いもnotesに記入してください。
JSONの `actual_count`、`actual_count_outside_mask` と各結果の実人数も未記入です。
実人数の自動推定、人数差だけによる見逃し・誤検知の自動判定は行いません。
件数の増加だけで精度向上と判断せず、各人への枠、重複枠、物への枠を確認してください。

## 今回の結果（2026-10-05）

入力は `IMG/demo.png`（1024×572）。設定はconf=0.25、IoU=0.7、personのみ、CPUです。
`demo-v1.json` の同じ4矩形をそのまま使用しました（4つとも同じ座標のため黒塗りの実効領域は1つ）。
座標や元画像は変更していません。

| 条件 | マスクなし人数 | 時間ms | マスクあり人数 | 時間ms |
| --- | ---: | ---: | ---: | ---: |
| YOLO11n / 640 | 13 | 41.6 | 11 | 39.2 |
| YOLO11n / 1280 | 25 | 147.0 | 18 | 104.4 |
| YOLO11s / 1280 | 26 | 341.4 | 20 | 282.9 |

時間はウォームアップ後3回の中央値で、入力前処理・推論・NMSを含むpredict呼出しの実測時間です。
モデル読込み、描画、保存は含みません。各反復の値もJSONに残しています。
PC負荷やキャッシュで変動するため、本番配信の性能を保証する数値ではありません。
imgsz=1280は入力の拡大であり、元画像にない細部が復元されるわけではありません。
実人数・見逃し・誤検知は利用者の目視確認待ちです。ライブ映像や複数カメラの精度検証には含めません。

保存先：`.camera-runtime/model-comparisons/20261005-133515-a326fd8a/`
