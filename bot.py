import os
import re
import json
import asyncio
from urllib.parse import urlparse
from pathlib import Path

from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from playwright.async_api import async_playwright

TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN','').strip()
OUT = Path('runtime')
OUT.mkdir(exist_ok=True)

WEBOOK_RE = re.compile(r"https?://(?:www\.)?webook\.com/[^\s]+", re.I)


def valid_webook(url: str) -> bool:
    try:
        p = urlparse(url)
        return p.scheme in {'http','https'} and p.hostname in {'webook.com','www.webook.com'}
    except Exception:
        return False


def extract_public_metadata(html: str):
    soup = BeautifulSoup(html, 'html.parser')
    data = {}
    if soup.title and soup.title.string:
        data['title'] = ' '.join(soup.title.string.split())

    # OpenGraph metadata is intentionally public page metadata.
    for prop, key in [('og:title','title'),('og:description','description'),('og:image','image')]:
        tag = soup.find('meta', attrs={'property': prop})
        if tag and tag.get('content'):
            data[key] = tag['content'].strip()

    # JSON-LD event metadata, when present publicly.
    for script in soup.find_all('script', attrs={'type':'application/ld+json'}):
        try:
            obj = json.loads(script.string or '')
        except Exception:
            continue
        items = obj if isinstance(obj, list) else [obj]
        for item in items:
            if not isinstance(item, dict):
                continue
            typ = item.get('@type')
            if typ == 'Event' or (isinstance(typ, list) and 'Event' in typ):
                data.setdefault('title', item.get('name'))
                data['startDate'] = item.get('startDate')
                loc = item.get('location')
                if isinstance(loc, dict):
                    data['location'] = loc.get('name')
                offers = item.get('offers')
                if isinstance(offers, dict):
                    data['price'] = offers.get('price')
                    data['priceCurrency'] = offers.get('priceCurrency')
                break
    return {k:v for k,v in data.items() if v}


async def inspect_webook(url: str):
    shot = OUT / 'webook.png'
    result = {'url': url, 'warnings': []}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1440, 'height': 1100},
            locale='ar-SA',
            user_agent=(
                'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                '(KHTML, like Gecko) Chrome/140.0 Safari/537.36'
            ),
        )
        page = await context.new_page()
        try:
            resp = await page.goto(url, wait_until='domcontentloaded', timeout=45000)
            result['status'] = resp.status if resp else None
            await page.wait_for_timeout(5000)
            html = await page.content()
            result.update(extract_public_metadata(html))

            # Publicly rendered text only. Do not attempt to bypass login, CAPTCHA, queues,
            # access controls, private APIs, or hidden organizer analytics.
            body_text = await page.locator('body').inner_text(timeout=10000)
            text = ' '.join(body_text.split())

            availability_words = []
            for phrase in ['متاح','غير متاح','نفدت','Sold out','Available','Unavailable','SAR','ر.س']:
                if phrase.lower() in text.lower():
                    availability_words.append(phrase)
            if availability_words:
                result['public_signals'] = availability_words

            # Prefer a visible seat-map-like region if the page exposes one.
            selectors = [
                '[class*="seat-map" i]', '[class*="seatmap" i]', '[id*="seat-map" i]',
                '[class*="venue-map" i]', '[class*="map-container" i]', 'canvas', 'svg'
            ]
            captured = False
            for sel in selectors:
                try:
                    loc = page.locator(sel).first
                    if await loc.count() and await loc.is_visible():
                        box = await loc.bounding_box()
                        if box and box['width'] > 350 and box['height'] > 220:
                            await loc.screenshot(path=str(shot))
                            result['screenshot_kind'] = 'map_candidate'
                            captured = True
                            break
                except Exception:
                    pass
            if not captured:
                await page.screenshot(path=str(shot), full_page=False)
                result['screenshot_kind'] = 'page'
                result['warnings'].append('لم أجد عنصر خريطة واضحًا؛ أرسلت لقطة من صفحة الحجز الظاهرة.')

            # Detect access hurdles without trying to evade them.
            lower = text.lower()
            hurdle_terms = ['captcha','verify you are human','cloudflare','طابور','queue','تسجيل الدخول','login']
            if any(t in lower for t in hurdle_terms):
                result['warnings'].append('الصفحة تعرض تحقق/دخول/طابور؛ البوت لن يتجاوز هذه الحماية.')

        finally:
            await context.close()
            await browser.close()

    result['screenshot'] = str(shot) if shot.exists() else None
    return result


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        'أرسل رابط فعالية من Webook وسأفحص البيانات العامة الظاهرة وأرسل لقطة للخريطة/صفحة الحجز.\n\n'
        'ملاحظة: المبيعات الفعلية ودفعات الطرح لا تظهر إلا إذا كانت منشورة للعامة؛ لن أتجاوز تسجيل الدخول أو حماية المنصة.'
    )


async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    text = msg.text or ''
    match = WEBOOK_RE.search(text)
    if not match:
        await msg.reply_text('أرسل رابط Webook كامل للفعالية.')
        return
    url = match.group(0).rstrip(').,]}>')
    if not valid_webook(url):
        await msg.reply_text('الرابط لازم يكون من webook.com.')
        return

    await msg.chat.send_action('upload_photo')
    try:
        data = await inspect_webook(url)
    except Exception as e:
        await msg.reply_text(f'تعذر فتح الصفحة حاليًا: {type(e).__name__}. جرّب الرابط مرة أخرى لاحقًا.')
        return

    lines = []
    if data.get('title'):
        lines.append(f"🎟 {data['title']}")
    if data.get('startDate'):
        lines.append(f"🗓 {data['startDate']}")
    if data.get('location'):
        lines.append(f"📍 {data['location']}")
    if data.get('price'):
        lines.append(f"💳 السعر المنشور: {data['price']} {data.get('priceCurrency','')}")
    if data.get('public_signals'):
        lines.append('👀 إشارات ظاهرة: ' + '، '.join(data['public_signals']))

    lines.append('📊 المبيعات: لا يمكن تأكيد رقم مبيعات إلا إذا نشرته Webook للعامة.')
    lines.append('🔄 الدفعات القادمة: تُعرض فقط إذا كانت مواعيد الطرح منشورة على الصفحة.')
    for w in data.get('warnings', []):
        lines.append('⚠️ ' + w)
    caption = '\n'.join(lines)[:1000]

    shot = data.get('screenshot')
    if shot and Path(shot).exists():
        with open(shot, 'rb') as f:
            await msg.reply_photo(photo=f, caption=caption)
    else:
        await msg.reply_text(caption)


async def main():
    if not TOKEN:
        raise SystemExit('Set TELEGRAM_BOT_TOKEN first')
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    await app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    asyncio.run(main())
