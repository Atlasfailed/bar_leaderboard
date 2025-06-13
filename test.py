import pandas as pd
df = pd.read_parquet('data/nation_rankings.parquet')
# See what top_contributors looks like for the UK
print(df.loc[df.countryCode=='GB', 'top_contributors'])
