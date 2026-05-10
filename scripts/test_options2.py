from nselib import derivatives
from datetime import date

df = derivatives.fno_bhav_copy(trade_date="08-05-2026")
print(f"total rows: {len(df)}")
print(f"unique TckrSymb (head 10): {df['TckrSymb'].unique()[:10]}")
print(f"unique FinInstrmTp: {df['FinInstrmTp'].unique()}")
nifty_all = df[df['TckrSymb'] == 'NIFTY']
print(f"NIFTY rows: {len(nifty_all)}")
print(f"NIFTY FinInstrmTp: {nifty_all['FinInstrmTp'].unique()}")
print(nifty_all.head(3)[['TckrSymb','FinInstrmTp','XpryDt','StrkPric','OptnTp','ClsPric']])
