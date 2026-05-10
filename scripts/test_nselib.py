from nselib import derivatives
import traceback

print("=== expiry dates NIFTY ===")
try:
    print(derivatives.expiry_dates_option_index())
except Exception as e:
    print("FAIL:", e); traceback.print_exc()

print("\n=== live option chain NIFTY ===")
try:
    df = derivatives.nse_live_option_chain("NIFTY")
    print(f"  type={type(df).__name__}")
    if hasattr(df, "shape"):
        print(f"  shape={df.shape}")
        print(f"  cols={list(df.columns)[:15]}")
        print(df.head(3))
except Exception as e:
    print("FAIL:", e); traceback.print_exc()
