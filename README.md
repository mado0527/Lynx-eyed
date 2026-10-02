# Lynx-eyed

Django と MySQL を使うアプリケーションです。

## 開発環境（Windows / PowerShell）

確認済みの環境は Python 3.13、MySQL 8.0 です。

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

既存の `.env` がある場合はコピーせず、その設定を使ってください。
`.env` の `SECRET_KEY` と MySQL の接続設定をローカル環境に合わせて編集します。
キーは次のコマンドで生成できます。

```powershell
.venv/Scripts/python.exe -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

MySQL を起動し、未作成の場合は管理者で接続して開発用データベースとユーザーを作成します。
パスワードは `.env` と同じ値に置き換えてください。

```sql
CREATE DATABASE lounge_db CHARACTER SET utf8mb4;
CREATE USER 'lynx_dev'@'127.0.0.1' IDENTIFIED BY 'replace-with-your-local-password';
GRANT ALL PRIVILEGES ON lounge_db.* TO 'lynx_dev'@'127.0.0.1';
```

```powershell
.venv/Scripts/python.exe manage.py check
.venv/Scripts/python.exe manage.py migrate
.venv/Scripts/python.exe manage.py runserver 127.0.0.1:8000
```

利用者向けトップ画面は http://127.0.0.1:8000/ 、管理画面は http://127.0.0.1:8000/admin/ です。
トップ画面は場所を選んで「更新」を押すと最新の混雑記録を再取得します。
トップ画面の混雑率は記録の利用人数と場所の現在の定員から計算し、保存された混雑率は変更しません。
最終計測日時は記録の日時を日本時間で表示します。同時刻の記録は記録IDが大きい方を選びます。
利用人数の推移は選択場所の直近20件を計測日時の古い順（同時刻は記録ID順）で表示します。

### 混雑記録の自動計算

`CrowdLog.objects.create(location=location, user_count=count, recorded_at=timestamp)`
またはインスタンスの `save()` で、新規保存時と人数・場所の変更時に混雑率を自動計算します。
共通処理は `crowd_app.calculations.calculate_crowd_rate` です。
小数第1位まで四捨五入し、定員0以下は `None`（DBではNULL）、0人は0%、定員超過は100%超で保存します。
管理画面で混雑率の入力は不要です。

既存の手入力値は自動補正しません。日時だけの編集や場所の定員変更でも過去の保存値は維持します。
人数や場所を修正した記録は、保存時の現在の定員で再計算します。
トップ画面は現在の定員で計算するため、定員変更後や過去の手入力値とは異なることがあります。
保存時の定員そのものを保持するフィールドは現在ありません。

将来のカメラ解析では上記の `create()` / `save()` を使用してください。
`bulk_create()`、`bulk_update()`、`QuerySet.update()`、直接SQLは `save()` を呼ばないため、自動計算を実行しません。
管理画面へのログイン用ユーザーが必要な場合は次を実行します。

```powershell
.venv/Scripts/python.exe manage.py createsuperuser
```

仮想環境の有効化は任意です。上記のコマンドは PowerShell の実行ポリシーを変更せず使用できます。
`.env` と `.venv` は Git の管理対象外です。

## 確認

```powershell
.venv/Scripts/python.exe -m pip check
.venv/Scripts/python.exe manage.py check
.venv/Scripts/python.exe manage.py makemigrations --check --dry-run
.venv/Scripts/python.exe manage.py test crowd_app
```

`requirements.txt` は、このリポジトリの既存仮想環境で動作確認したバージョンを固定しています。
