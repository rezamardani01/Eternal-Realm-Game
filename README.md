# قلمرو جاودان (Eternal Realm)

ربات بازی نقش‌آفرینی اجتماعی برای گروه‌های **بله**. هر بازیکن یک شخصیت دائمی دارد که در همه گروه‌ها یکسان است؛
بازی اصلی داخل گروه‌ها انجام می‌شود: ماهیگیری، معدن، شکار، دوئل با ریپلای، خرید و فروش و ارتقای تجهیزات.

ساخته‌شده با [Baleropy](https://github.com/rezamardani01/Baleropy) و SQLite.

## راه‌اندازی

```bash
python -m venv .venv
.venv\Scripts\activate          # ویندوز
pip install -r requirements.txt
copy config.example.toml config.toml   # سپس توکن و owner_id را در config.toml بنویسید
python main.py
```

دیتابیس به‌صورت خودکار در `data/game.db` ساخته و مهاجرت‌ها اجرا می‌شوند.

## تست

```bash
pip install -r requirements-dev.txt
pytest
```
