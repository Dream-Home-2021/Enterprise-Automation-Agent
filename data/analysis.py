1. import pandas as pd
2. import numpy as np
3. from sklearn.model_selection import train_test_split
4. from sklearn.preprocessing import StandardScaler, OneHotEncoder
5. from sklearn.compose import ColumnTransformer
6. from sklearn.pipeline import Pipeline
7. from sklearn.ensemble import RandomForestRegressor
8. from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
9. import matplotlib.pyplot as plt
10. import seaborn as sns
11. # Load data
12. df = pd.read_csv('1122.csv')
13. print('Shape:', df.shape)
14. print('Columns:', df.columns.tolist())
15. print('Data types:')
16. print(df.dtypes)
