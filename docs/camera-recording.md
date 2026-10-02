# 223教室：人数検知→MySQL→トップ画面の接続検証

## 保存先と保存処理

今回の場所はラウンジではなく223教室です。既存の場所名「223」は1件で、場所ID=1、定員25人です。
場所マスターを追加・変更せず使用しました。

`tools/camera_preview.py`をWebサーバーとは別プロセスで実行します。
既定ではプレビューのみでDB接続・保存はしません。`--save-db`と`--location-id`の両方が必要です。
`tools/db_recording.py`がDjango設定を初期化し、config/settings.pyが既存.envを読み込みます。認証情報はログに出しません。
`CrowdLog.objects.create()`を使い、既存モデルのsave()とcalculate_crowd_rateを再利用します。

- 人数：正常に推論できたフレームのperson検知数。正常0人は保存します。
- 混雑率：人数÷保存時点の場所の定員×100。小数第1位。定員0以下はNULL、100%超を許可します。
- 計測日時：フレーム取得成功時刻。UTCで保存し、トップ画面は日本時間で表示します。
- マスキング：なし。検知の誤差は補正・架空値で置き換えません。
- 映像取得・推論・DB保存の失敗：エラー種別を記録して停止。失敗を0人として保存しません。停止前に成功した記録は残します。
- 保存ログ：`.camera-runtime/logs/recording-*.log`。認証情報を含めず、保存ID・人数・率・日時・失敗種別を記録します。

## 起動（Windows / VS Code PowerShell）

Webサーバー用ターミナル：

```powershell
$env:DEBUG='True'
.venv/Scripts/python.exe manage.py runserver 127.0.0.1:8000 --noreload
```

すでに起動中なら2つ目を起動せず再利用してください。.envは変更しません。

解析用の別ターミナル（通常5分間隔、ヘッドレス）：

```powershell
.venv/Scripts/python.exe tools/camera_preview.py --save-db --location-id 1 --headless
```

プレビューも表示する場合は`--headless`を外します。
通常のintervalは300秒です。最初の正常な推論を保存し、保存完了から300秒後以降の新しいフレームを次に計測・保存します。
待機中も映像を読み進め、過去のフレームを5分間ためません。推論が長い場合はその時間が周期に加わります。

短い間隔で2件だけ検証して自動停止：

```powershell
.venv/Scripts/python.exe tools/camera_preview.py --save-db --location-id 1 --interval 5 --max-records 2 --headless
```

これも実DBに追加記録します。今回すでに2件の接続検証を実施しました。追加検証が不要なら繰り返さないでください。

DBに書き込まずプレビューだけ：

```powershell
.venv/Scripts/python.exe tools/camera_preview.py
```

停止：解析ターミナルでCtrl+C。プレビューがある場合はQ/Escまたはウィンドウを閉じます。
停止しても保存済みデータは削除しません。Webサーバーとは独立して停止できます。

## 今回の確認結果

入力：`http://192.168.0.134:8080/?action=stream`、OpenCVで1280×720を取得。
マスキングなし、confidence=0.25、NMS IoU=0.70。

| log_id | 場所ID | 人数 | 混雑率 | 最終計測日時（日本時間） |
|---|---:|---:|---:|---|
| 3 | 1 | 4 | 16% | 2026/10/02 15:52:52 |
| 4 | 1 | 3 | 12% | 2026/10/02 15:53:18 |

5秒間隔指定で2件保存後、自動停止。初回はモデル起動・推論に時間がかかるため、計測日時の差は単純な5秒ではありません。
初回の計測日時はモデル初期化前に取得したフレームの時刻を維持しています。
トップ画面の更新リクエスト相当のGETで最新log_id=4、3人、12%、15:53:18を確認。
従来の混雑記録2件・場所マスター・.envの内容が変更されていないことも照合しました。

## Workbenchとブラウザーでのユーザー確認

Workbenchの既存接続で、現在のDBを選択して以下の読み取りSQLを実行してください。

```sql
SELECT log_id, location_id, user_count, crowd_rate,
       recorded_at AS measured_at_utc,
       DATE_ADD(recorded_at, INTERVAL 9 HOUR) AS measured_at_jst
FROM crowd_log
WHERE location_id = 1
ORDER BY recorded_at DESC, log_id DESC
LIMIT 5;
```

最新のlog_id=4に3人・12%があることを確認します。
Djangoのこの構成ではrecorded_atはUTCで保存されるため、Workbenchの生の時刻は06:53:18、日本時間換算は15:53:18です。

ブラウザーで http://127.0.0.1:8000/?location=1 を開き、ヘッダーの更新ボタンを押します。
3人／定員25人、12%、最終計測日時2026/10/02 15:53:18、グラフの最新記録が一致することを確認してください。
後から別の記録が追加されていれば、最新の記録で比較してください。
WorkbenchのGUI操作とブラウザーの目視はユーザー確認待ちです。HTTP応答・ORMの照合は実施済みです。

## 未検証・残る事項

- マスキング座標は未確定。勝手に適用していません。
- 223教室での接続検証です。ラウンジでの検知精度・設置条件の検証ではありません。
- 検知人数は実人数とずれることがあります。今回の3人・4人は検知値で、実人数がその値だったと保証しません。
- 通常の300秒間隔の長時間運用と復旧運用は未検証。短い間隔の実接続と周期保存のテストを実施しています。
- トップ画面は現在の定員で混雑率を再計算します。定員を後で変更すると過去の保存率と異なる場合があります。過去記録を勝手に変更しません。
- 映像公開配信・予測機能は追加していません。
