# نشر التطبيق على الويب

هذه الحزمة جاهزة للنشر كتطبيق Streamlit.

## Streamlit Community Cloud
1. ارفع هذا المجلد إلى مستودع GitHub خاص بك.
2. افتح Streamlit Community Cloud واختر المستودع و`app.py`.
3. في Settings > Secrets أضف:

```toml
FRED_API_KEY = "YOUR_FRED_API_KEY"
US500_TICKER = "^GSPC"
REFRESH_MINUTES = 30
```

4. Deploy. سيعطيك Streamlit رابط HTTPS عام يمكن فتحه من iPhone والكمبيوتر.

## مهم
- لا تضع FRED API key داخل GitHub.
- `^GSPC` هو proxy عام لـ S&P 500، وليس بالضرورة نفس سعر US500 لدى وسيطك.
- SQLite مناسب للتجربة/تطبيق شخصي بسيط؛ للنشر العام متعدد المستخدمين استخدم PostgreSQL.
