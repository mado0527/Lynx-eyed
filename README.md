# Lynx-eyed

カメラ映像から人を検出し、場所ごとの利用人数・混雑率をWebサイトで確認するアプリケーションです。OpenCVとYOLO11nで人数を検出し、Djangoを通じてMySQLへ記録します。

## 処理の流れ

```text
カメラ映像
  → OpenCVでフレーム取得
  → 指定した除外領域を黒塗り（任意）
  → YOLO11nでpersonだけを検出・人数を算出
  → 人数・計測日時・混雑率をMySQLに保存（保存モードのみ）
  → Djangoで記録を取得・集計
  → HTML / CSS / JavaScriptでサイトに表示
```

カメラ処理とWebサーバーは別のプロセスです。サイトを開くだけではカメラ検出は起動しません。検出人数は各フレームの人物検出枠数で、人物追跡や入退室人数の累計ではありません。

## 主な機能

| 機能 | 内容 |
| --- | --- |
| 人数検出 | YOLO11nによる人物検出・プレビュー・静止画像入力 |
| マスキング | 選択した長方形を黒塗りし、検出対象から除外 |
| 計測記録 | 明示的に有効化した場合、標準で5分間隔でDB保存 |
| トップページ | 場所別の最新人数・混雑率・計測日時・直近20件の推移 |
| 曜日別グラフ | 当月の保存済み曜日別集計を優先し、なければ直近4・8・12週間の記録から集計 |
| 混雑予測画面 | 保存済みの当日の未来の予測値と当日の実測値を表示 |
| 管理者画面 | 認証・権限確認、月別集計、端末・カメラ情報の閲覧 |
| データ管理 | Django管理画面で場所・定員・記録などを編集 |

混雑予測を自動生成する処理と、サイト内のライブ映像配信は未実装です。カメラ処理は混雑記録を追加しますが、予測値は生成しません。

## フォルダ構成と役割

| 場所 | 処理・用途 |
| --- | --- |
| `config/settings.py` | MySQL接続、タイムゾーンなどのDjango設定 |
| `config/urls.py` | URLと画面処理の対応 |
| `tools/camera_preview.py` | 映像取得・モデル読み込み・人物検出・プレビュー |
| `tools/camera_masking.py` | 除外領域の選択・JSON保存・黒塗り・比較 |
| `tools/db_recording.py` | カメラの検出結果をDjango ORMで保存 |
| `tools/compare_detections.py` | 検出条件の比較 |
| `tools/compare_image_models.py` | モデル・画像サイズの比較実験 |
| `crowd_app/models.py` | DBテーブル定義・保存時の混雑率計算 |
| `crowd_app/calculations.py` | 混雑率の共通計算 |
| `crowd_app/views.py` | 利用者画面のデータ取得・集計 |
| `crowd_app/prediction_chart.py` | 予測・実測グラフの座標と線の作成 |
| `crowd_app/management.py` | 管理者認証・権限確認・月別集計 |
| `crowd_app/admin.py` | Django管理画面の設定 |
| `crowd_app/communication.py`、`middleware.py` | 通信エラーの判定・エラー画面表示 |
| `crowd_app/templates/` | 画面のHTML |
| `crowd_app/migrations/` | DB構造の変更履歴 |
| `static/crowd_app/` | CSS・JavaScript・ロゴ画像 |
| `docs/` | 操作手順・比較実験・画面検証の記録 |
| `IMG/` | 検証用画像 |
| `.camera-runtime/` | モデル・マスク・確認画像・ログ（Git管理外） |

トップページのHTMLは `crowd_app/templates/crowd_app/home.html`、デザインは `static/crowd_app/home.css`、ロゴは `static/crowd_app/lynx-eyed-logo.png` です。

## 開発環境の準備（Windows / PowerShell）

既存手順で確認している環境はPython 3.13、MySQL 8.0です。リポジトリのルートで実行します。仮想環境の有効化は任意です。

### 1. Python環境

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 2. 環境変数

`.env` がない場合だけコピーしてください。既存の設定はそのまま使います。

```powershell
Copy-Item .env.example .env
```

`.env.example` のホスト・ポートは仮の値です。`.env` を実際の接続先に合わせて編集し、`SECRET_KEY` と `DEBUG` も設定します。

```dotenv
SECRET_KEY=生成したキーに置き換える
DEBUG=True
DB_NAME=lounge_db
DB_USER=lynx_dev
DB_PASSWORD=ローカルのパスワードに置き換える
DB_HOST=127.0.0.1
DB_PORT=3306
```

キーを生成するコマンド：

```powershell
.\.venv\Scripts\python.exe -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

`.env` はGit管理対象外です。同名のプロセス環境変数がある場合は、そちらが優先されます。

### 3. MySQL

MySQLを起動し、未作成の場合はMySQLの管理者で次のSQLを実行します。パスワードは `.env` と同じ値に置き換えてください。

```sql
CREATE DATABASE lounge_db CHARACTER SET utf8mb4;
CREATE USER 'lynx_dev'@'127.0.0.1' IDENTIFIED BY 'replace-with-your-local-password';
GRANT ALL PRIVILEGES ON lounge_db.* TO 'lynx_dev'@'127.0.0.1';
```

### 4. テーブル・管理者の作成と起動

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

`http://127.0.0.1:8000/admin/` にログインし、「場所マスター」で場所名と最大定員を登録します。カメラの記録には登録した場所のIDを使用します。

## カメラの準備・起動

カメラへの接続確認、人数検出、マスク設定、DB保存、停止方法は、[カメラ起動コマンド（camera-commands.md）](docs/camera-commands.md) を参照してください。配信URLや場所IDは、使用するカメラとデータベースに合わせて指定します。

初回のカメラ用依存パッケージとYOLO11nモデルの準備は、[カメラプレビューの準備](docs/camera-preview.md#準備) を参照してください。

## Web画面

| URL | 内容 | 処理 |
| --- | --- | --- |
| `/` | 最新の混雑状況・人数推移 | `views.py` の `home()` |
| `/prediction-graph/` | 当日の予測・実測グラフ | `prediction_graph()` |
| `/weekly-graph/` | 曜日別平均人数 | `weekly_graph()` |
| `/help/` | 使い方 | `information_page()` |
| `/live/` | ライブ映像の案内（配信未実装） | `information_page()` |
| `/management/` | 管理者ダッシュボード | `management.py` |
| `/device-management/` | 端末・カメラ情報 | `device_management()` |
| `/admin/` | データ編集 | `admin.py` |

処理ファイルは `crowd_app/` 内にあります。管理機能はDjangoのユーザー認証と権限を使用します。

トップ画面で場所を選んで更新すると、最新のDB記録を読み直します。`/?realtime=1` は2秒ごとにページを再読み込みしますが、カメラの計測間隔は変わりません。日時は日本時間で表示します。

## データと混雑率

主要モデルは、場所の `LocationMaster`、計測記録の `CrowdLog`、カメラの `CameraInfo`、端末の `DeviceInfo` です。ほかに予測・集計用の `CrowdPrediction`、`WeeklySummaryLog`、`DayOfWeekSummaryLog`、`MonthlyReport`、管理者情報用の `AdminInfo` を定義しています。

```text
混雑率（%）＝ 利用人数 ÷ 最大定員 × 100
```

計算は `crowd_app/calculations.py` の `calculate_crowd_rate()` に共通化しています。

- 小数第1位まで四捨五入します。0人は0%、定員超過は100%超になります。
- 定員0以下は算出不可（DBではNULL）です。
- `CrowdLog.objects.create()` / インスタンスの `save()` で、新規保存時と人数・場所の変更時に自動計算します。
- 日時だけの編集や定員変更では、過去の保存済み混雑率は変更しません。保存時の定員自体を保持する項目はありません。
- トップ画面は現在の定員で再計算するため、保存済み混雑率と異なる場合があります。

`bulk_create()`、`bulk_update()`、`QuerySet.update()`、直接SQLはモデルの `save()` を呼ばないため、この自動計算を実行しません。

## 確認・テスト

依存関係とDjango設定を確認：

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe manage.py check
```

実際のMySQLに接続せず、テスト用のインメモリSQLiteでDB構造とWeb機能を確認：

```powershell
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run --settings=config.test_settings
.\.venv\Scripts\python.exe manage.py test crowd_app --settings=config.test_settings
```

カメラ処理のテスト（カメラ用依存パッケージが必要）：

```powershell
.\.venv\Scripts\python.exe -m unittest tools.test_camera_preview tools.test_camera_masking
```

検出精度は、これらのテストに加えて実際の映像で検出漏れ・誤検出を目視確認してください。

## 関連ドキュメント

- [カメラ起動・マスク設定・通常運用](docs/camera-commands.md)
- [DB記録の手順・検証](docs/camera-recording.md)
- [マスキングの仕様・検証](docs/camera-masking.md)
- [モデル比較](docs/model-comparison.md)
- [YOLO11とYOLO26の比較](docs/yolo11-yolo26-comparison.md)

検証記録には各時点の実装状況が含まれます。通常の起動操作は `camera-commands.md`、実際の引数や処理はコードを確認してください。
