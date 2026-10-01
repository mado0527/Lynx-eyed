import os
from pathlib import Path
from dotenv import load_dotenv  # ★追加

BASE_DIR = Path(__file__).resolve().parent.parent

# ★ .env ファイルの読み込み
load_dotenv(BASE_DIR / '.env')

# ★ SECRET_KEYを環境変数から取得
SECRET_KEY = os.getenv('SECRET_KEY')

# ...（中略）...

# ★ DATABASES設定を環境変数から取得
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.getenv('DB_NAME', 'lounge_db'),
        'USER': os.getenv('DB_USER', 'root'),
        'PASSWORD': os.getenv('DB_PASSWORD', ''),
        'HOST': os.getenv('DB_HOST', '127.0.0.1'),
        'PORT': os.getenv('DB_PORT', '3306'),
        'OPTIONS': {
            'charset': 'utf8mb4',
        },
    }
}