import yfinance as yf
import traceback

for sym in ["^NSEI", "NSEI.NS", "NIFTYBEES.NS"]:
    print(f"=== {sym} ===")
    try:
        t = yf.Ticker(sym)
        opts = t.options
        print(f"  available expiries: {opts}")
        if opts:
            chain = t.option_chain(opts[0])
            print(f"  calls: {len(chain.calls)} puts: {len(chain.puts)}")
            print(chain.calls.head(3))
    except Exception as e:
        print("FAIL:", e); traceback.print_exc()
