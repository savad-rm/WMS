import os

import pandas as pd

df = pd.read_excel(
    'C:\\Users\\Savad\\Desktop\\Pmg\\WMS\\Client Docs\\Work scedule  Bakertilly Office.xlsx',
    engine='openpyxl')


first_column_data = df.iloc[:, 1]

print(first_column_data)