# منصة إدارة حسابات Telegram — Railway

تطبيق ويب عربي مبني بـ FastAPI وPostgreSQL. يربط حسابات Telegram عبر Telethon، يخزن الجلسات مشفرة، يدير الروابط والأرصدة، ويشغل المهام بالتتابع مع احترام FloodWait.

## تنبيه أمني

لا تضع `BOT_TOKEN` أو `API_HASH` أو مفاتيح التشفير في GitHub. جلسة Telegram تمنح وصولاً للحساب؛ استخدم التطبيق فقط بموافقة صاحب الحساب والتزم بشروط Telegram.

## التشغيل المحلي

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

أنشئ مفتاح تشفير:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

عدّل `.env`، أنشئ PostgreSQL، ثم:

```bash
alembic upgrade head
uvicorn app.main:app --reload
```

افتح `http://localhost:8000`.

## الرفع إلى GitHub

```bash
git init
git add .
git commit -m "Initial Railway web platform"
git branch -M main
git remote add origin https://github.com/USERNAME/REPOSITORY.git
git push -u origin main
```

## النشر على Railway

1. أنشئ Project جديدًا وأضف PostgreSQL.
2. اختر **Deploy from GitHub Repo** وحدد المستودع.
3. أضف متغيرات الخدمة:

```env
APP_NAME=منصة إدارة حسابات Telegram
ENVIRONMENT=production
SECRET_KEY=<random-64+-chars>
SESSION_ENCRYPTION_KEY=<fernet-key>
DATABASE_URL=${{Postgres.DATABASE_URL}}
TELEGRAM_API_ID=<your-api-id>
TELEGRAM_API_HASH=<your-api-hash>
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<strong-password>
PUBLIC_REGISTRATION=true
DEFAULT_USER_BALANCE=0
MAX_LINKS_PER_BATCH=500
MAX_ACCOUNTS_PER_USER=10
```

4. سيقرأ Railway `railway.json` ويشغل migrations ثم Uvicorn.
5. من Settings → Networking اختر **Generate Domain**.

## ملاحظات تشغيلية

- استخدم Replica واحدة فقط؛ عامل المهام موجود داخل عملية التطبيق.
- للتحميل الكبير افصل العامل إلى Railway Service مستقلة وأضف Redis أو صف مهام.
- تغيير `SESSION_ENCRYPTION_KEY` يفقد القدرة على فك الجلسات القديمة.
- عند الاشتباه بتسريب جلسة، ألغِها من تطبيق Telegram الرسمي.
