from sca.ingestion.news_rss import fetch_all_news, apply_flags

items = fetch_all_news()
items = apply_flags(items)
print(f"total: {len(items)}")
src_counts = {}
for n in items:
    src_counts[n.source] = src_counts.get(n.source, 0) + 1
for k, v in src_counts.items():
    print(f"  {k}: {v}")
print("\nFirst 5 headlines:")
for n in items[:5]:
    flags = "[" + ",".join(n.flags) + "]" if n.flags else ""
    print(f"  {flags} {n.headline[:100]}")
