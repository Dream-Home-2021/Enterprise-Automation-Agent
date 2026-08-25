1. Next step in research process:
2. 1. Load the dataset 1122.csv (already loaded).
3. 2. Perform exploratory data analysis (EDA):
4.    - Check data shape, column names, data types.
5.    - Check for missing values.
6.    - Compute basic statistics (mean, median, std) for numeric columns (the consumption columns).
7.    - Examine distribution of key consumption columns (e.g., 聚屏平台合约消费20231113, 手百开屏消费20231113, etc.).
8.    - Look at categorical variables: 发证机关所在市, 管理员, 订单行.
9.    - Visualize correlations among consumption columns.
10. 3. Feature engineering ideas:
11.    - Create total consumption per row (sum of all consumption columns).
12.    - Create day-over-day change features (e.g., 20231114 - 20231113).
13.    - Aggregate consumption by ad type across days.
14. 4. Formulate hypothesis:
15.    Example: 'Total consumption on 20231114 is positively correlated with total consumption on 20231113, with a slope close to 1 for stable advertisers.'
16.    Another: 'Advertisers in certain cities (e.g., 厦门市) have higher平均消费 than others.'
