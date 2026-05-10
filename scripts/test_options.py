from sca.ingestion.nse_options_chain import fetch_option_chain, chain_to_dataframe
import traceback

for sym in ["NIFTY", "BANKNIFTY"]:
    print(f"=== {sym} ===")
    try:
        raw = fetch_option_chain(sym)
        df = chain_to_dataframe(raw)
        print(f"  rows={len(df)}")
        if not df.empty:
            print(f"  expiries={df['expiry'].nunique()}")
            print(f"  spot={df['underlying'].dropna().iloc[0]}")
            exps = sorted(df['expiry'].dropna().dt.strftime('%Y-%m-%d').unique())
            print(f"  first 6 expiries: {exps[:6]}")
        else:
            print(f"  raw keys: {list(raw.keys())[:5] if isinstance(raw, dict) else 'not dict'}")
    except Exception as e:
        print(f"  FAIL: {e}")
        traceback.print_exc()
