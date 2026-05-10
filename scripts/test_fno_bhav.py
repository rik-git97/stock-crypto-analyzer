from nselib import derivatives
from datetime import date, timedelta
import traceback

# Try Friday's bhav copy (today is Sunday 2026-05-10, Friday = 2026-05-08)
for d in [date(2026, 5, 8), date(2026, 5, 7), date(2026, 5, 6)]:
    s = d.strftime("%d-%m-%Y")
    print(f"=== fno_bhav_copy {s} ===")
    try:
        df = derivatives.fno_bhav_copy(trade_date=s)
        print(f"  shape={df.shape}")
        if df.shape[0] > 0:
            print(f"  cols={list(df.columns)[:30]}")
            print(df.head(3))
            break
    except Exception as e:
        print("FAIL:", e)
