# Webook Telegram Bot

بوت تيليجرام يستقبل رابط فعالية من Webook ويعرض البيانات العامة الظاهرة ويلتقط لقطة للخريطة/صفحة الحجز عندما تكون متاحة للمتصفح.

## 1) إنشاء البوت
من Telegram افتح **@BotFather** ثم:
- `/newbot`
- اختر الاسم والـ username
- انسخ الـ token

## 2) التثبيت
يتطلب Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
playwright install chromium
```

## 3) التشغيل
Linux/macOS:
```bash
export TELEGRAM_BOT_TOKEN='ضع_التوكن_هنا'
python bot.py
```

Windows PowerShell:
```powershell
$env:TELEGRAM_BOT_TOKEN='ضع_التوكن_هنا'
python bot.py
```

## ما الذي يفعله؟
- يقبل فقط روابط `webook.com`.
- يقرأ metadata العامة من الصفحة.
- يحاول تصوير عنصر يشبه خريطة المقاعد إذا كان ظاهرًا، وإلا يرسل لقطة الصفحة.
- لا يتجاوز CAPTCHA أو تسجيل الدخول أو الطابور أو أي حماية وصول.
- لا يدّعي رقم مبيعات أو موعد دفعة إلا إذا كانت المعلومة منشورة للعامة.

## التطوير المقترح
يمكن إضافة قاعدة بيانات لحفظ لقطات دورية من التوفر العام ومقارنة التغيرات بمرور الوقت. هذا يعطي **تغير المخزون الظاهر** وليس رقم مبيعات مؤكدًا، لأن الإلغاء والحجز المؤقت وتغييرات المخزون قد تؤثر على الأرقام.
