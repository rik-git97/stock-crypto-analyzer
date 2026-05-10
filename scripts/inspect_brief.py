import json, sys
with open("output/live/brief_2026-05-10.json", encoding="utf-8") as f:
    b = json.load(f)
print("capital_portfolio present:", b.get("capital_portfolio") is not None)
if b.get("capital_portfolio"):
    cp = b["capital_portfolio"]
    print(f"  positions: {len(cp['positions'])} deployed: {cp['deployed_pct']:.2%} cash: {cp['cash_residual']:,.0f}")
    for p in cp["positions"][:5]:
        print(f"    {p['ticker']:15s} {p['shares']:>4} shares @ {p['last_price']:>8.2f} = {p['allocated']:>10,.0f}")
print("\noptions_ideas:", len(b.get("options_ideas") or []))
for o in (b.get("options_ideas") or []):
    print(f"  {o['underlying']} {o['spread_type']} exp={o['expiry']} ({o['days_to_expiry']}d) "
          f"strikes={o['long_strike']:.0f}/{o['short_strike']:.0f} debit={o['capital_required']:.0f} "
          f"maxP={o['max_profit_per_lot']:.0f} maxL={o['max_loss_per_lot']:.0f} rr=1:{o['risk_reward']:.2f}")
print("\nnews_per_ticker (non-empty):", sum(1 for v in (b.get("news_per_ticker") or {}).values() if v))
print("health_summary:", b.get("health_summary"))
print("\nnotes:")
for n in b.get("notes") or []:
    print(" -", n)
