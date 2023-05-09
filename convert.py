import datamart_profiler
import pandas as pd
df = pd.DataFrame({'states':['France', 'Alpes', 'Lombardy', 'Bavaria'], 'pincodes':['75001', '69001', '20121', '80331'],})
df.to_parquet("sample.parquet")
metadata = datamart_profiler.process_dataset("sample.parquet")
print("Metadata: ", metadata)
