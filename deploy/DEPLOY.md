# دليل النشر على خادم VPS (Ubuntu/Debian) — بدون Docker

مسار المصادقة الافتراضي في الملفات: الرمز في `/srv/http_sms` والمستخدم `httpsms`.
إذا غيّرت أي مسار عدّل ملفات `deploy/*.service` والمتابّع.

## 1) تجهيز النظام

```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-pip \
    git redis-server postgresql postgresql-contrib nginx certbot python3-certbot-nginx
```

## 2) إضافة مستخدم للنشر وإنزال الكود

```bash
sudo useradd -r -m -d /srv/http_sms -s /bin/bash httpsms
sudo mkdir -p /srv/http_sms
sudo git clone <repo-url> /srv/http_sms        # أو انقل الملفات يدوياً
sudo chown -R httpsms:httpsms /srv/http_sms
```

## 3) البيئة الافتراضية والاعتماديات

```bash
sudo -u httpsms bash -c 'cd /srv/http_sms && python3 -m venv venv'
sudo -u httpsms bash -c 'cd /srv/http_sms && ./venv/bin/pip install -r requirements.txt'
```

## 4) قاعدة البيانات (PostgreSQL)

```bash
sudo -u postgres psql
```

```sql
CREATE USER httpsms WITH PASSWORD 'STRONG_DB_PASSWORD';
CREATE DATABASE httpsms OWNER httpsms;
\q
```

## 5) ملف .env

```bash
sudo -u httpsms cp /srv/http_sms/.env.example /srv/http_sms/.env
sudo -u httpsms nano /srv/http_sms/.env
```

القيم المطلوبة للإنتاج:

```ini
SECRET_KEY=<ناتج الأمر التالي>
DEBUG=False
ALLOWED_HOSTS=sms.example.com
DATABASE_URL=postgres://httpsms:STRONG_DB_PASSWORD@127.0.0.1:5432/httpsms
REDIS_URL=redis://127.0.0.1:6379/0
SECURE_SSL_REDIRECT=True
SECURE_HSTS_SECONDS=31536000
TRUSTED_PROXY=True
WEBHOOK_SECRET=<مفتاح عشوائي>
```

توليد المفتاح السري:

```bash
sudo -u httpsms bash -c 'cd /srv/http_sms && ./venv/bin/python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"'
```

> **ترانزيل هام:** النظام الآن يرفض الإقلاع في وضع الإنتاج إذا ظل SECRET_KEY هو الافتراضي
> `django-insecure-...` (خطأ `ImproperlyConfigured`).

## 6) الترحيلات والملفات الثابتة والمشرف

```bash
sudo -u httpsms bash -c 'cd /srv/http_sms && ./venv/bin/python manage.py migrate'
sudo -u httpsms bash -c 'cd /srv/http_sms && ./venv/bin/python manage.py collectstatic --noinput'
export DJANGO_SUPERUSER_USERNAME=admin
export DJANGO_SUPERUSER_PASSWORD='STRONG_PASSWORD'
export DJANGO_SUPERUSER_EMAIL=admin@example.com
sudo -u httpsms bash -c 'cd /srv/http_sms && ./venv/bin/python manage.py createsuperuser --noinput'
sudo chown -R httpsms:httpsms /srv/http_sms
```

## 7) تشغيل الخدمات الثلاث (systemd)

```bash
sudo cp /srv/http_sms/deploy/httpsms-web.service \
        /srv/http_sms/deploy/httpsms-worker.service \
        /srv/http_sms/deploy/httpsms-beat.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now httpsms-web httpsms-worker httpsms-beat
```

فحص الحالة:

```bash
systemctl status httpsms-web httpsms-worker httpsms-beat
journalctl -u httpsms-web -f          # سجلات الويب
journalctl -u httpsms-worker -f       # سجلات الرسائل
```

## 8) nginx + HTTPS

```bash
sudo cp /srv/http_sms/deploy/nginx.conf /etc/nginx/sites-available/httpsms
sudo sed -i 's/YOUR_DOMAIN/sms.example.com/g' /etc/nginx/sites-available/httpsms
sudo ln -sf /etc/nginx/sites-available/httpsms /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d sms.example.com
```

شبكة الـ WebSocket للأجهزة يجب أن تصل عبر: `wss://sms.example.com/ws/device/`.

## 9) التحقق من الجاهزية (كل الأوامر على الخادم)

```bash
# فحص أمان Django عام
sudo -u httpsms bash -c 'cd /srv/http_sms && ./venv/bin/python manage.py check --deploy'

# المتصفح: https://sms.example.com/api/docs/
# واجهة الإدارة: https://sms.example.com/admin/
```

| الاختبار | الأمر / التوقع |
|---|---|
| Swagger | `curl -sk https://sms.example.com/api/docs/` → 200 |
| الدخول | `POST /api/v1/auth/login/` بالإيميل وكلمة المرور → يطلع `access`+`refresh` |
| WebSocket | افتح `wss://sms.example.com/ws/device/` مع `device_uuid`+`token` → `device.state` |
| اختبار الاختبارات الكامل | `./venv/bin/python manage.py test tests --settings=httpsms.test_settings` → `OK` |

## ملاحظات

- دائماً `SECURE_SSL_REDIRECT=True` + `TRUSTED_PROXY=True` خلف nginx، وإلا فقد تحدث حلقة تحويل.
- يشغّل Celery beat المهام التلقائية (استرجاع المهام العالقة، انتهاء الصلاحية، إغلاق الأجهزة، التقرير اليومي).
- الترقية لاحقاً: `git pull` ثم `migrate` + `collectstatic` ثم `systemctl restart httpsms-web httpsms-worker`.