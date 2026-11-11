# مینی‌اپ قلمرو جاودان (Bale Mini App)

رابط گرافیکی بازی برای مینی‌اپ بله. منطق بازی، دیتابیس و پرداخت همان ربات است؛ این پوشه فقط صفحه را می‌سازد و
`eternal_realm/web/` رابط HTTP آن است که داخل همان پردازش ربات اجرا می‌شود.

## ساختار

| مسیر | کار |
|---|---|
| `src/pages/Realm.tsx` | نقشه‌ی قلمرو: ساختمان‌ها و HUD |
| `src/pages/Hero.tsx` · `Adventure.tsx` · `Clan.tsx` · `Market.tsx` | چهار تب دیگر |
| `src/pages/Wheel.tsx` · `PathTrack.tsx` · `Battle.tsx` | صحنه‌های اختصاصی: گردونه، مسیر قهرمانی، میدان نبرد |
| `src/pages/Panel.tsx` | هر پنل دیگر ربات، به شکل پنجره‌ی بازی یا صحنه‌ی گفتگو |
| `src/icons/*.json` | نگاشت ایموجی‌ها و شناسه‌های بازی به آیکون |
| `scripts/build-icons.mjs` | آیکون‌های لازم را از بسته‌ی دانلودشده به `public/icons/` می‌برد |
| `eternal_realm/web/server.py` · `scenes.py` · `bridge.py` · `auth.py` | API، صحنه‌ها، پل پنل‌ها، اعتبارسنجی `initData` |

## پیش‌نمایش محلی (بدون بله)

```bash
python scripts/miniapp_preview.py
```

```bash
npm --prefix miniapp install
```

```bash
npm --prefix miniapp run dev
```

پیش‌نمایش دیتابیس جدای خودش را دارد (`data/miniapp_preview.db`) و ربات واقعی را روشن نمی‌کند.
`http://localhost:5173/?splash` صفحه‌ی آغاز را نگه می‌دارد.

## انتشار

1. بعد از هر تغییر در صفحه: `npm --prefix miniapp run build` و پوشه‌ی `miniapp/dist` را هم کامیت کنید
   (سرور Node ندارد و همین خروجی ساخته‌شده را نشان می‌دهد).
2. یک بار روی سرور، با دامنه‌ای که به سرور اشاره می‌کند:

   ```bash
   sudo bash /opt/eternal-realm/deploy/setup-miniapp.sh play.example.com
   ```

   این اسکریپت Caddy را با HTTPS خودکار نصب می‌کند، بخش `[miniapp]` را در `config.toml` روشن می‌کند و ربات را
   دوباره راه می‌اندازد. از آن به بعد دکمه‌ی «🎮 باز کردن مینی اپ» در ردیف اول منوی اصلی ربات دیده می‌شود.
3. (اختیاری) در @botfather مینی‌اپ اصلی ربات را هم روی همان آدرس تنظیم کنید.

## امنیت

- هر درخواست `Bale.WebApp.initData` را می‌فرستد و سرور امضای آن را با توکن ربات می‌سنجد.
- صفحه هیچ جایزه یا خریدی را خودش ثبت نمی‌کند؛ همه‌چیز با همان سرویس‌های ربات انجام می‌شود.
- پرداخت: سرور سفارش می‌سازد و `createInvoiceLink` می‌گیرد، صفحه `openInvoice` را باز می‌کند و تحویل فقط با
  `successful_payment` در ربات انجام می‌شود.

## تصویرها و فونت‌ها

- آیکون‌ها: [game-icons.net](https://game-icons.net) با مجوز CC BY 3.0 (بسته‌ی `@iconify-json/game-icons`).
- فونت‌ها: Vazirmatn و Lalezar با مجوز OFL (بسته‌های `@fontsource`).
