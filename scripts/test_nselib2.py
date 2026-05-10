from nselib import derivatives
from datetime import date, timedelta
import traceback

print("=== option_price_volume_data NIFTY 28-Jul-2026 ===")
try:
    today = date.today()
    from_d = (today - timedelta(days=7)).strftime("%d-%m-%Y")
    to_d = today.strftime("%d-%m-%Y")
    df = derivatives.option_price_volume_data(
        symbol="NIFTY", instrument="OPTIDX",
        from_date=from_d, to_date=to_d,
        option_type="CE", expiry_date="28-Jul-2026", strike_price=26000,
    )
    print(f"  type={type(df).__name__}")
    if hasattr(df, "shape"):
        print(f"  shape={df.shape}")
        if df.shape[0] > 0:
            print(df.tail(3))
except Exception as e:
    print("FAIL:", e); traceback.print_exc()

print("\n=== fno_bhav_copy ===")
try:
    today = date.today()
    yesterday = (today - timedelta(days=1)).strftime("%d-%m-%Y")
    df = derivatives.fno_bhav_copy(trade_date=yesterday)
    print(f"  shape={df.shape}")
    print(f"  cols={list(df.columns)[:20]}")
    nifty_ops = df[df.iloc[:,0].astype(str).str.contains("NIFTY", na=False)] if df.shape[1] > 0 else df
    print(f"  nifty rows: {len(nifty_ops)}")
    print(nifty_ops.head(3))
except Exception as e:
    print("FAIL:", e); traceback.print_exc()
