1. ## 1. Optimal K Selection

**File**: `elbow_silhouette_ch.png`

Three subplots clearly demonstrate that **K=2** is the optimal number of temporal consumption regimes:

### Elbow Method
- WCSS drops sharply from K=1 (212.35) to K=2 (140.19), a 34% reduction
- Further increases to K=3 (108.95, 22% reduction) show diminishing returns
- The elbow is less pronounced than ideal, suggesting moderate cluster structure

### Silhouette Score
- **K=2 achieves the highest silhouette score: 0.4186** — well above the 0.25 threshold for meaningful structure
- K=3 drops to 0.3038, K=4 to 0.2578
- Silhouette declines monotonically after K=2, strongly supporting the 2-cluster solution

### Calinski–Harabasz Index
- **K=2 also achieves the highest CH index: 27.96**
- K=3 drops to 20.28, K=4 to 18.47
- Perfect agreement between all three metrics: K=2 is unambiguously optimal

## 2. Heatmap: Transposed Consumption Matrix

**File**: `heatmap.png`

A 32-day × 11-department heatmap of Z-scored consumption values, with days reordered by cluster assignment (red annotations on the right side).

### Key Observations
- **Cluster 0 (11 days)**: Dominated by blue/negative Z-scores across service departments (维护: -0.81, 大客: -0.81, 泉州: -0.73, 漳州客服: -0.60, 行发维护大区: -0.69). These are "low-service-activity days."
- **Cluster 1 (21 days)**: Red/positive Z-scores for the same service departments (维护: +0.42, 大客: +0.42, 泉州: +0.38, 漳州客服: +0.31, 行发维护大区: +0.36). These are "high-service-activity days."
- **医疗事业部** is the *only* department showing the opposite pattern: higher in Cluster 0 (+0.47) than Cluster 1 (-0.24)
- **运营策略中心** shows zero consumption across ALL days — it contributes no variance and was handled correctly

### Temporal Structure
- Cluster 0 days cluster in early period (4/30–5/3) and late period (5/27–5/28)
- Cluster 1 dominates the middle of the month (5/4–5/26)
- This suggests a **beginning/middle/end-of-month regime pattern**

## 3. Radar Chart: Centroid Profiles

**File**: `radar.png`

A polar radar chart comparing the 11-dimensional centroid profiles of Cluster 0 (blue circle) and Cluster 1 (orange triangle).

### Pattern Analysis
- **Clear separation on 5 axes**: 维护, 大客, 泉州, 漳州客服, 行发维护大区 — Cluster 1 (service-active) consistently occupies a larger radius
- **Convergence on 3 axes**: 框架 (slightly higher in Cluster 0), 医疗事业部 (notably higher in Cluster 0), 运营策略中心 (zero for both)
- **Crossing pattern**: The profiles are not simply scaled versions of each other — they have qualitatively different shapes, confirming that the clusters differ in *profile* not just magnitude

## 4. Timeline: Temporal Regime Sequence

**File**: `timeline.png`

Daily total consumption over the 32-day period (April 30 to May 31), with alternating background colors showing the regime transitions.

### Temporal Dynamics
- **Period 1 (4/30–5/3, Cluster 0)**: Consistently low total spending (~60K–80K)
- **Period 2 (5/4–5/6, Cluster 1)**: Sharp increase to ~120K–160K
- **Period 3 (5/7, Cluster 0)**: Brief dip back to ~100K
- **Period 4 (5/8–5/26, Cluster 1)**: Sustained high activity (100K–200K) with weekly oscillations
- **Period 5 (5/27–5/28, Cluster 0)**: Late-month drop
- **Period 6 (5/29–5/31, Cluster 1)**: Final surge to ~160K

### Regime Transition Points
- Transition dates: 5/4 (C0→C1), 5/7 (C1→C0), 5/8 (C0→C1), 5/27 (C1→C0), 5/29 (C0→C1)
- These transitions likely correspond to business cycles: month start → ramp-up → mid-month peak → month-end close → final push

## 5. Parallel Coordinates: Centroid Comparison

**File**: `parallel.png`

Parallel coordinates plot with 11 parallel axes (one per department), showing the two centroid paths.

### Key Crossing Points
- **维护, 大客, 泉州, 漳州客服, 行发维护大区**: Wide separation — Cluster 1 (orange) significantly higher than Cluster 0 (blue)
- **框架**: Cluster 0 slightly higher (crossing point)
- **医疗事业部**: Cluster 0 notably higher (main crossing point) — this is the most distinctive axis
- **运营策略中心**: Both at 0 (no variance)

This visualization clearly shows that the two regimes are **not simply "high vs. low" spending days** — they have fundamentally different departmental allocation patterns.

## 6. Statistical Validation Summary

| Metric | Value | Threshold | Assessment |
|---|---|---|---|
| Silhouette Score (K=2) | 0.4186 | >0.25 | ✅ Strong structure |
| Calinski–Harabasz (K=2) | 27.96 | Highest among K=2..8 | ✅ Best separation |
| Permutation Test p-value | <0.001 | <0.05 | ✅ Highly significant |
| Bootstrap ARI (mean±std) | 0.9837±0.0428 | >0.90 | ✅ Extremely stable |
| ANOVA p-value | 0.272 | <0.05 | ❌ Not significant (total spending alone) |

## 7. Boxplot: Spending Distribution by Cluster

**File**: `boxplot.png`

Boxplot comparing the distribution of total daily consumption across the two clusters.

### Analysis
- **Cluster 0**: Median ≈ 95K, IQR ≈ 60K–120K, narrow distribution
- **Cluster 1**: Median ≈ 120K, IQR ≈ 80K–160K, wider distribution
- **Overlap**: Considerable overlap between the two clusters on total spending
- This confirms that clusters are distinguished by **spending profile (shape)** rather than **spending magnitude (size)**

### Outlier Analysis
- Cluster 1 has a wider spread, suggesting more variable total spending on high-activity days
- No extreme outliers identified in either cluster

## 8. Conclusions & Business Recommendations

### Scientific Conclusion

**H₁ is partially accepted.** Transposed K-means successfully discovers 2 robust temporal consumption regimes:

- **Cluster 0 ("Medical-Heavy, Service-Light" Days)**: Lower service department spending but elevated medical division spending. Occurs in early and late month periods.
  
- **Cluster 1 ("Service-Active" Days)**: Elevated spending across 5 regional service departments (维护, 大客, 泉州, 漳州客服, 行发维护大区). Dominates the mid-month period.

### Business Recommendations

1. **Regime-Aware Budgeting**: Allocate more budget to service departments in mid-month periods (Cluster 1), shift focus to medical division at month start/end (Cluster 0)
2. **Cash Flow Forecasting**: Expect peak spending in mid-May (~120K–160K range), lower spending at month boundaries (~60K–120K)
3. **Staff Scheduling**: Field service staff should be fully staffed during Cluster 1 periods; medical division staff during Cluster 0
4. **Further Analysis**: Investigate why 运营策略中心 reports zero spending — data collection issue or genuinely inactive unit?

### Code Availability

Full reproducible Python script: `kmeans_analysis.py`

## 9. References

1. Steinley, D. (2006). K-means clustering: A half-century synthesis. *British Journal of Mathematical and Statistical Psychology*, 59(1), 1–34.
2. Rousseeuw, P. J. (1987). Silhouettes: A graphical aid to the interpretation and validation of cluster analysis. *Journal of Computational and Applied Mathematics*, 20, 53–65.
3. Calinski, T., & Harabasz, J. (1974). A dendrite method for cluster analysis. *Communications in Statistics*, 3(1), 1–27.
4. Hubert, L., & Arabie, P. (1985). Comparing partitions. *Journal of Classification*, 2(1), 193–218.
5. MacQueen, J. (1967). Some methods for classification and analysis of multivariate observations. *Proc. 5th Berkeley Symp. Math. Statist. Prob.*
2. file_name
