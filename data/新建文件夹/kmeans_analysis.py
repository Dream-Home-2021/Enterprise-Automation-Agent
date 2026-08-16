#!/usr/bin/env python3
"""K-Means Temporal Consumption Regime Discovery on Department-Level Daily Spending.

This script performs a transposed K-means clustering analysis on the 1122.csv
dataset (11 departments × 32 days), treating each day as an observation with
11 departmental spending features. It includes optimal K selection, clustering,
visualization, and statistical validation.
"""

import os
import sys
import random
import warnings
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats
from scipy.spatial.distance import pdist, squareform
from sklearn.cluster import KMeans
from sklearn.metrics import calinski_harabasz_score, silhouette_score, adjusted_rand_score
from sklearn.preprocessing import StandardScaler

import matplotlib
matplotlib.use('Agg')  # Non-interactive backend for saving figures
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib.patches import Patch
from matplotlib.lines import Line2D

import seaborn as sns

# ---------------------------------------------------------------------------
# Global configuration
# ---------------------------------------------------------------------------
DATA_FILE = '1122.csv'
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in dir() else '.'
RANDOM_SEED = 42

# Lock all random seeds for reproducibility
random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)
os.environ['PYTHONHASHSEED'] = str(RANDOM_SEED)

warnings.filterwarnings('ignore', category=FutureWarning)
warnings.filterwarnings('ignore', category=UserWarning)

# ---------------------------------------------------------------------------
# 1. Data Loading & Preprocessing
# ---------------------------------------------------------------------------

def load_and_preprocess(filepath: str) -> Tuple[pd.DataFrame, np.ndarray, np.ndarray, List[str], List[str]]:
    """Load CSV, drop the 环比 column, transpose, and Z-score normalize.

    Args:
        filepath: Path to the CSV file (11 departments x 33 columns: 32 days + 环比).

    Returns:
        df_raw: Original wide-form DataFrame (departments x days).
        X_norm: Normalized transposed matrix, shape (n_days, n_departments).
        day_labels: List of day column names (e.g., '4月30日', ...).
        dept_names: List of department names.
        total_daily: 1-D array of total spending per day.
    """
    df_raw = pd.read_csv(filepath, encoding='utf-8-sig')
    # Identify department column and day columns
    dept_col = '部门'
    # Columns to drop: 环比 column
    drop_cols = [c for c in df_raw.columns if '环比' in c or '环比' in c]
    df_days = df_raw.drop(columns=drop_cols, errors='ignore')
    
    dept_names = df_days[dept_col].tolist()
    day_cols = [c for c in df_days.columns if c != dept_col]
    day_labels = day_cols

    # Matrix: shape (n_depts, n_days)
    X_dept_day = df_days[day_cols].values.astype(np.float64)
    
    # Transpose -> (n_days, n_depts)
    X_day_dept = X_dept_day.T  # shape (32, 11)
    
    # Total daily spending
    total_daily = X_day_dept.sum(axis=1)
    
    # Z-score normalization per department column
    scaler = StandardScaler()
    X_norm = scaler.fit_transform(X_day_dept)  # shape (32, 11)
    
    print(f"Data loaded: {X_norm.shape[0]} days x {X_norm.shape[1]} departments")
    print(f"Departments: {dept_names}")
    print(f"Day range: {day_labels[0]} to {day_labels[-1]}")
    print(f"Total daily spending range: {total_daily.min():.2f} ~ {total_daily.max():.2f}")
    print()
    
    return df_raw, X_norm, day_labels, dept_names, total_daily


# ---------------------------------------------------------------------------
# 2. Optimal K Determination
# ---------------------------------------------------------------------------

def determine_optimal_k(
    X: np.ndarray,
    k_range: range = range(2, 9),
    n_init: int = 100,
    random_state: int = RANDOM_SEED,
) -> Tuple[int, Dict[int, float], Dict[int, float], Dict[int, float]]:
    """Run K-means for multiple K values and compute quality metrics.

    Args:
        X: Data matrix, shape (n_samples, n_features).
        k_range: Candidate cluster counts.
        n_init: Number of K-means initializations per K.
        random_state: Random seed.

    Returns:
        optimal_k: Chosen K (argmax of silhouette score).
        wcss_dict: {k: within-cluster sum of squares}.
        sil_dict: {k: silhouette score}.
        ch_dict: {k: Calinski-Harabasz index}.
    """
    wcss_dict: Dict[int, float] = {}
    sil_dict: Dict[int, float] = {}
    ch_dict: Dict[int, float] = {}

    print("=" * 60)
    print("Optimal K Determination")
    print("=" * 60)

    for k in k_range:
        km = KMeans(n_clusters=k, n_init=n_init, max_iter=500,
                    random_state=random_state)
        labels = km.fit_predict(X)
        wcss_dict[k] = km.inertia_
        sil_dict[k] = silhouette_score(X, labels)
        ch_dict[k] = calinski_harabasz_score(X, labels)
        print(f"K={k:2d} | WCSS={km.inertia_:>12.2f} | Silhouette={sil_dict[k]:.4f} | CH={ch_dict[k]:>8.2f}")

    # Select optimal K: prefer silhouette, break ties with CH
    best_k = max(sil_dict, key=sil_dict.get)  # type: ignore
    print(f"\nOptimal K* = {best_k} (highest Silhouette = {sil_dict[best_k]:.4f})")
    print()

    return best_k, wcss_dict, sil_dict, ch_dict


# ---------------------------------------------------------------------------
# 3. Final K-Means Model
# ---------------------------------------------------------------------------

def run_final_kmeans(
    X: np.ndarray,
    n_clusters: int,
    n_init: int = 50,
    max_iter: int = 500,
    random_state: int = RANDOM_SEED,
) -> Tuple[np.ndarray, np.ndarray, KMeans]:
    """Fit final K-means model and return labels, centroids, and model.

    Args:
        X: Data matrix, shape (n_samples, n_features).
        n_clusters: Number of clusters.
        n_init: Number of K-means initializations.
        max_iter: Maximum iterations per run.
        random_state: Random seed.

    Returns:
        labels: Cluster assignments for each day, shape (n_days,).
        centroids: Cluster centroids, shape (n_clusters, n_features).
        model: Fitted KMeans object.
    """
    model = KMeans(n_clusters=n_clusters, n_init=n_init, max_iter=max_iter,
                   random_state=random_state)
    labels = model.fit_predict(X)
    centroids = model.cluster_centers_
    print(f"Final K-means: K={n_clusters}, inertia={model.inertia_:.2f}")
    return labels, centroids, model


# ---------------------------------------------------------------------------
# 4. Visualization Helpers
# ---------------------------------------------------------------------------

def plot_elbow_silhouette_ch(
    wcss: Dict[int, float],
    sil: Dict[int, float],
    ch: Dict[int, float],
    save_path: str,
) -> str:
    """Plot elbow curve, silhouette scores, and Calinski-Harabasz indices.

    Args:
        wcss: {k: WCSS}.
        sil: {k: silhouette}.
        ch: {k: Calinski-Harabasz}.
        save_path: Output file path.

    Returns:
        save_path.
    """
    ks = sorted(wcss.keys())
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    # Elbow
    ax = axes[0]
    ax.plot(ks, [wcss[k] for k in ks], 'bo-', linewidth=2, markersize=8)
    ax.set_xlabel('Number of clusters (K)', fontsize=12)
    ax.set_ylabel('Within-cluster sum of squares (WCSS)', fontsize=12)
    ax.set_title('Elbow Method', fontsize=13, fontweight='bold')
    ax.grid(True, alpha=0.3)
    ax.set_xticks(ks)

    # Silhouette
    ax = axes[1]
    ax.plot(ks, [sil[k] for k in ks], 'rs-', linewidth=2, markersize=8)
    ax.axhline(y=0.25, color='gray', linestyle='--', alpha=0.6, label='Threshold (0.25)')
    best_k = max(sil, key=sil.get)  # type: ignore
    ax.plot(best_k, sil[best_k], 'g*', markersize=15, label=f'Best K={best_k}')
    ax.set_xlabel('Number of clusters (K)', fontsize=12)
    ax.set_ylabel('Silhouette Score', fontsize=12)
    ax.set_title('Silhouette Score', fontsize=13, fontweight='bold')
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.set_xticks(ks)

    # Calinski-Harabasz
    ax = axes[2]
    ax.plot(ks, [ch[k] for k in ks], 'g^-', linewidth=2, markersize=8)
    best_k_ch = max(ch, key=ch.get)  # type: ignore
    ax.plot(best_k_ch, ch[best_k_ch], 'r*', markersize=15, label=f'Best K={best_k_ch}')
    ax.set_xlabel('Number of clusters (K)', fontsize=12)
    ax.set_ylabel('Calinski-Harabasz Index', fontsize=12)
    ax.set_title('Calinski-Harabasz Index', fontsize=13, fontweight='bold')
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.set_xticks(ks)

    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"Saved: {save_path}")
    return save_path


def plot_heatmap(
    X: np.ndarray,
    labels: np.ndarray,
    day_labels: List[str],
    dept_names: List[str],
    save_path: str,
) -> str:
    """Plot a heatmap of days x departments with cluster annotations.

    Args:
        X: Normalized data matrix, shape (n_days, n_depts).
        labels: Cluster labels for each day.
        day_labels: List of day names.
        dept_names: List of department names.
        save_path: Output file path.

    Returns:
        save_path.
    """
    n_days = len(day_labels)
    n_depts = len(dept_names)
    
    # Create a DataFrame for the heatmap
    df_heat = pd.DataFrame(
        X,
        index=[f"Day {i+1}" for i in range(n_days)],
        columns=dept_names,
    )
    df_heat['Cluster'] = labels
    # Sort by cluster
    df_heat = df_heat.sort_values('Cluster')
    
    # Color bar for clusters
    unique_labels = sorted(np.unique(labels))
    n_clusters = len(unique_labels)
    cluster_colors = sns.color_palette('Set2', n_clusters)
    row_colors = [cluster_colors[lab] for lab in df_heat['Cluster']]
    
    # Drop cluster column for heatmap
    data_for_heat = df_heat.drop(columns='Cluster')
    
    g = sns.clustermap(
        data_for_heat,
        row_cluster=False,
        col_cluster=True,
        row_colors=row_colors,
        cmap='RdBu_r',
        center=0,
        vmin=-2, vmax=2,
        figsize=(14, 10),
        linewidths=0.5,
        linecolor='gray',
        xticklabels=True,
        yticklabels=True,
        dendrogram_ratio=(0.1, 0.15),
        cbar_pos=(0.02, 0.8, 0.03, 0.15),
    )
    
    # Add legend for clusters
    legend_elements = [
        Patch(facecolor=cluster_colors[i], label=f'Cluster {i}')
        for i in unique_labels
    ]
    g.ax_heatmap.legend(
        handles=legend_elements,
        loc='upper left',
        bbox_to_anchor=(1.02, 1),
        title='Cluster',
        frameon=True,
    )
    
    g.fig.suptitle('Daily Spending Profiles: Days x Departments (Normalized)',
                   fontsize=14, fontweight='bold', y=1.02)
    
    g.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close(g.fig)
    print(f"Saved: {save_path}")
    return save_path


def plot_radar_centroids(
    centroids: np.ndarray,
    dept_names: List[str],
    save_path: str,
) -> str:
    """Plot a radar chart of centroid profiles.

    Args:
        centroids: Cluster centroids, shape (n_clusters, n_depts).
        dept_names: Department names.
        save_path: Output file path.

    Returns:
        save_path.
    """
    n_clusters, n_depts = centroids.shape
    angles = np.linspace(0, 2 * np.pi, n_depts, endpoint=False).tolist()
    angles += angles[:1]  # Close the polygon

    fig, ax = plt.subplots(figsize=(10, 10), subplot_kw={'polar': True})
    colors = sns.color_palette('Set2', n_clusters)

    for i in range(n_clusters):
        values = centroids[i].tolist()
        values += values[:1]  # Close the polygon
        ax.plot(angles, values, 'o-', linewidth=2, color=colors[i],
                label=f'Cluster {i}')
        ax.fill(angles, values, alpha=0.1, color=colors[i])

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(dept_names, fontsize=9)
    ax.set_title('Centroid Profiles by Cluster (Z-score Normalized)',
                 fontsize=14, fontweight='bold', pad=30)
    ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1), fontsize=10)
    ax.grid(True, alpha=0.4)

    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"Saved: {save_path}")
    return save_path


def plot_timeline(
    total_daily: np.ndarray,
    labels: np.ndarray,
    day_labels: List[str],
    save_path: str,
) -> str:
    """Plot time series of total daily consumption colored by cluster.

    Args:
        total_daily: Total spending per day.
        labels: Cluster labels.
        day_labels: Day names.
        save_path: Output file path.

    Returns:
        save_path.
    """
    n_days = len(day_labels)
    x = np.arange(n_days)
    unique_labels = sorted(np.unique(labels))
    n_clusters = len(unique_labels)
    colors = sns.color_palette('Set2', n_clusters)

    fig, ax = plt.subplots(figsize=(16, 6))

    # Background stripe per cluster
    for i in unique_labels:
        mask = labels == i
        ax.fill_between(x, 0, total_daily.max() * 1.1,
                         where=mask, color=colors[i], alpha=0.08,
                         label=f'Cluster {i}')

    # Line plot
    ax.plot(x, total_daily, 'k-', linewidth=1.5, alpha=0.7, zorder=3)
    # Scatter points colored by cluster
    for i in unique_labels:
        mask = labels == i
        ax.scatter(x[mask], total_daily[mask], color=colors[i],
                   s=80, edgecolors='black', linewidth=0.5, zorder=4, label=f'Cluster {i}')

    # X-axis ticks
    step = max(1, n_days // 16)
    tick_indices = range(0, n_days, step)
    ax.set_xticks(list(tick_indices))
    ax.set_xticklabels([day_labels[i] for i in tick_indices], rotation=45, ha='right', fontsize=9)

    ax.set_xlabel('Day', fontsize=12)
    ax.set_ylabel('Total Daily Consumption', fontsize=12)
    ax.set_title('Temporal Consumption Regimes: Daily Total Spending by Cluster',
                 fontsize=14, fontweight='bold')
    ax.legend(fontsize=10, loc='upper left')
    ax.grid(True, alpha=0.3)
    ax.set_xlim(-0.5, n_days - 0.5)

    # Format y-axis with comma separator
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f'{v:,.0f}'))

    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"Saved: {save_path}")
    return save_path


def plot_parallel_coordinates(
    centroids: np.ndarray,
    dept_names: List[str],
    save_path: str,
) -> str:
    """Plot parallel coordinates of centroid profiles.

    Args:
        centroids: Cluster centroids, shape (n_clusters, n_depts).
        dept_names: Department names.
        save_path: Output file path.

    Returns:
        save_path.
    """
    n_clusters, n_depts = centroids.shape
    colors = sns.color_palette('Set2', n_clusters)

    fig, ax = plt.subplots(figsize=(14, 6))
    x = np.arange(n_depts)

    for i in range(n_clusters):
        ax.plot(x, centroids[i], 'o-', linewidth=2, color=colors[i],
                markersize=8, label=f'Cluster {i}')

    ax.set_xticks(x)
    ax.set_xticklabels(dept_names, rotation=45, ha='right', fontsize=9)
    ax.set_xlabel('Department', fontsize=12)
    ax.set_ylabel('Normalized Spending (Z-score)', fontsize=12)
    ax.set_title('Parallel Coordinates: Cluster Centroid Profiles',
                 fontsize=14, fontweight='bold')
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.axhline(y=0, color='gray', linestyle='--', alpha=0.4)

    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"Saved: {save_path}")
    return save_path


def plot_boxplot_by_cluster(
    total_daily: np.ndarray,
    labels: np.ndarray,
    save_path: str,
) -> str:
    """Boxplot of daily total spending per cluster.

    Args:
        total_daily: Total spending per day.
        labels: Cluster labels.
        save_path: Output file path.

    Returns:
        save_path.
    """
    unique_labels = sorted(np.unique(labels))
    n_clusters = len(unique_labels)
    colors = sns.color_palette('Set2', n_clusters)

    data_by_cluster = [total_daily[labels == i] for i in unique_labels]

    fig, ax = plt.subplots(figsize=(10, 6))
    bp = ax.boxplot(data_by_cluster, patch_artist=True, widths=0.5,
                    medianprops={'color': 'black', 'linewidth': 2})

    for patch, color in zip(bp['boxes'], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)

    # Scatter jittered points
    for i, data in enumerate(data_by_cluster):
        jitter = np.random.normal(0, 0.04, size=len(data))
        ax.scatter(np.ones_like(data) * (i + 1) + jitter, data,
                   color=colors[i], alpha=0.7, s=40, edgecolors='black',
                   linewidth=0.5, zorder=3)

    ax.set_xticklabels([f'Cluster {i}\n(n={len(data_by_cluster[i])})'
                        for i in unique_labels])
    ax.set_xlabel('Cluster', fontsize=12)
    ax.set_ylabel('Total Daily Consumption', fontsize=12)
    ax.set_title('Distribution of Daily Total Spending by Cluster',
                 fontsize=14, fontweight='bold')
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f'{v:,.0f}'))
    ax.grid(True, axis='y', alpha=0.3)

    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"Saved: {save_path}")
    return save_path


# ---------------------------------------------------------------------------
# 5. Statistical Validation
# ---------------------------------------------------------------------------

def anova_validation(
    total_daily: np.ndarray,
    labels: np.ndarray,
) -> Tuple[float, float]:
    """Perform one-way ANOVA on total daily spending across clusters.

    Args:
        total_daily: Total spending per day.
        labels: Cluster labels.

    Returns:
        f_stat: ANOVA F-statistic.
        p_value: ANOVA p-value.
    """
    unique_labels = sorted(np.unique(labels))
    groups = [total_daily[labels == i] for i in unique_labels]
    f_stat, p_value = stats.f_oneway(*groups)
    print(f"ANOVA: F={f_stat:.4f}, p={p_value:.6f}")
    return f_stat, p_value


def permutation_test(
    X: np.ndarray,
    labels: np.ndarray,
    n_permutations: int = 1000,
    random_state: int = RANDOM_SEED,
) -> Tuple[float, float]:
    """Permutation test of silhouette score.

    Shuffle day labels and recompute silhouette to build a null distribution.

    Args:
        X: Normalized data matrix.
        labels: True cluster labels.
        n_permutations: Number of permutations.
        random_state: Random seed.

    Returns:
        observed_sil: Silhouette of true labels.
        p_value: Proportion of permuted silhouettes >= observed.
    """
    rng = np.random.RandomState(random_state)
    observed_sil = silhouette_score(X, labels)
    n_days = len(labels)
    perm_sils = np.zeros(n_permutations)

    for i in range(n_permutations):
        shuffled = labels[rng.permutation(n_days)]
        perm_sils[i] = silhouette_score(X, shuffled)

    p_value = np.mean(perm_sils >= observed_sil)
    print(f"Permutation test: observed Silhouette={observed_sil:.4f}, "
          f"p={p_value:.6f} (n_perm={n_permutations})")
    return observed_sil, p_value


def bootstrap_stability_check(
    X: np.ndarray,
    n_clusters: int,
    n_bootstrap: int = 500,
    sample_fraction: float = 0.8,
    random_state: int = RANDOM_SEED,
) -> float:
    """Bootstrap stability check using Adjusted Rand Index (ARI).

    Resample days with replacement, fit K-means, compare to original labels.

    Args:
        X: Normalized data matrix.
        n_clusters: Number of clusters.
        n_bootstrap: Number of bootstrap replicates.
        sample_fraction: Fraction of days to sample per bootstrap.
        random_state: Random seed.

    Returns:
        mean_ari: Mean ARI across bootstrap replicates.
    """
    rng = np.random.RandomState(random_state)
    n_days = X.shape[0]
    n_sample = max(2, int(n_days * sample_fraction))

    # Reference model on full data
    ref_model = KMeans(n_clusters=n_clusters, n_init=50, max_iter=500,
                       random_state=random_state)
    ref_labels = ref_model.fit_predict(X)

    aris = np.zeros(n_bootstrap)
    for i in range(n_bootstrap):
        indices = rng.choice(n_days, size=n_sample, replace=False)
        X_sample = X[indices]
        # Fit K-means on bootstrap sample
        boot_model = KMeans(n_clusters=n_clusters, n_init=20, max_iter=300,
                            random_state=random_state + i)
        boot_labels = boot_model.fit_predict(X_sample)
        # Predict labels for full data (assign to nearest centroid)
        full_labels = boot_model.predict(X)
        aris[i] = adjusted_rand_score(ref_labels, full_labels)

    mean_ari = float(np.mean(aris))
    std_ari = float(np.std(aris))
    print(f"Bootstrap stability: mean ARI={mean_ari:.4f} +/- {std_ari:.4f} "
          f"(n_bootstrap={n_bootstrap}, sample_frac={sample_fraction})")
    return mean_ari


# ---------------------------------------------------------------------------
# 6. Interpretation
# ---------------------------------------------------------------------------

def interpret_clusters(
    centroids: np.ndarray,
    dept_names: List[str],
    total_daily: np.ndarray,
    labels: np.ndarray,
) -> Dict[int, str]:
    """Generate human-readable interpretation for each cluster.

    Args:
        centroids: Cluster centroids, shape (n_clusters, n_depts).
        dept_names: Department names.
        total_daily: Total spending per day.
        labels: Cluster labels.

    Returns:
        cluster_desc: {cluster_id: description string}.
    """
    unique_labels = sorted(np.unique(labels))
    cluster_desc: Dict[int, str] = {}
    
    # Overall spending patterns per department
    dept_avg = total_daily.mean()
    
    for cid in unique_labels:
        mask = labels == cid
        n_days = mask.sum()
        cluster_total_avg = total_daily[mask].mean()
        rel_size = cluster_total_avg / dept_avg if dept_avg > 0 else 1.0
        
        # Top departments that are high (positive z-score) in this cluster
        centroid = centroids[cid]
        high_depts = []
        low_depts = []
        for j, dept in enumerate(dept_names):
            if centroid[j] > 0.5:
                high_depts.append(f"{dept}(+{centroid[j]:.2f})")
            elif centroid[j] < -0.5:
                low_depts.append(f"{dept}({centroid[j]:.2f})")
        
        # Spending level description
        if rel_size > 1.15:
            level = "HIGH"
        elif rel_size < 0.85:
            level = "LOW"
        else:
            level = "MEDIUM"
        
        # Build description
        desc_parts = [f"Regime {cid} ({n_days} days)"]
        desc_parts.append(f"Spending Level: {level} (avg={cluster_total_avg:,.0f}, "
                          f"rel={rel_size:.2f}x overall avg)")
        if high_depts:
            desc_parts.append(f"Elevated departments: {', '.join(high_depts[:5])}")
        if low_depts:
            desc_parts.append(f"Depressed departments: {', '.join(low_depts[:5])}")
        
        cluster_desc[cid] = ' | '.join(desc_parts)
    
    return cluster_desc


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def main() -> None:
    """Execute the full K-means analysis pipeline."""
    print("=" * 60)
    print("Temporal Consumption Regime Discovery via K-Means")
    print("=" * 60)
    print()

    # Step 1: Load and preprocess
    data_path = os.path.join(OUTPUT_DIR, DATA_FILE)
    if not os.path.exists(data_path):
        # Try current directory
        data_path = DATA_FILE
    df_raw, X_norm, day_labels, dept_names, total_daily = load_and_preprocess(data_path)

    # Step 2: Determine optimal K
    best_k, wcss_dict, sil_dict, ch_dict = determine_optimal_k(X_norm)

    # Step 3: Final K-means model
    labels, centroids, model = run_final_kmeans(X_norm, n_clusters=best_k)

    # Print cluster assignments
    print("\n--- Cluster Assignments ---")
    for i, (day, label) in enumerate(zip(day_labels, labels)):
        print(f"  {day:>8s} -> Cluster {label}")
    print()

    # Step 4: Visualizations
    print("--- Generating Visualizations ---")
    plot_elbow_silhouette_ch(wcss_dict, sil_dict, ch_dict,
                              os.path.join(OUTPUT_DIR, 'elbow_silhouette_ch.png'))
    plot_heatmap(X_norm, labels, day_labels, dept_names,
                 os.path.join(OUTPUT_DIR, 'heatmap.png'))
    plot_radar_centroids(centroids, dept_names,
                          os.path.join(OUTPUT_DIR, 'radar.png'))
    plot_timeline(total_daily, labels, day_labels,
                   os.path.join(OUTPUT_DIR, 'timeline.png'))
    plot_parallel_coordinates(centroids, dept_names,
                               os.path.join(OUTPUT_DIR, 'parallel.png'))
    plot_boxplot_by_cluster(total_daily, labels,
                             os.path.join(OUTPUT_DIR, 'boxplot.png'))
    print()

    # Step 5: Statistical validation
    print("--- Statistical Validation ---")
    anova_f, anova_p = anova_validation(total_daily, labels)
    obs_sil, perm_p = permutation_test(X_norm, labels, n_permutations=1000)
    mean_ari = bootstrap_stability_check(X_norm, n_clusters=best_k,
                                          n_bootstrap=500, sample_fraction=0.8)
    print()

    # Step 6: Interpretation
    print("--- Cluster Interpretation ---")
    cluster_desc = interpret_clusters(centroids, dept_names, total_daily, labels)
    for cid in sorted(cluster_desc.keys()):
        print(f"  {cluster_desc[cid]}")
    print()

    # Summary
    print("=" * 60)
    print("ANALYSIS SUMMARY")
    print("=" * 60)
    print(f"  Optimal K: {best_k}")
    print(f"  Silhouette Score: {sil_dict[best_k]:.4f}")
    print(f"  Calinski-Harabasz Index: {ch_dict[best_k]:.2f}")
    print(f"  ANOVA F-statistic: {anova_f:.4f} (p={anova_p:.6f})")
    print(f"  Permutation test p-value: {perm_p:.6f}")
    print(f"  Bootstrap Stability (mean ARI): {mean_ari:.4f}")
    print(f"  Significant at alpha=0.05: {'YES' if anova_p < 0.05 else 'NO'}")
    print(f"  Silhouette > 0.25 threshold: {'YES' if sil_dict[best_k] > 0.25 else 'NO'}")
    print()

    # Print centroid profiles
    print("--- Centroid Profiles (Z-score normalized) ---")
    header_parts = [f"{'Dept':<16s}"]
    for i in range(best_k):
        header_parts.append(f"  C{i:<10}")
    header = "".join(header_parts)
    print(header)
    print("-" * len(header))
    for j, dept in enumerate(dept_names):
        row_parts = [f"{dept:<16s}"]
        for i in range(best_k):
            row_parts.append(f"  {centroids[i, j]:>8.3f}  ")
        print("".join(row_parts))
    print()

    print("Analysis complete. All figures saved to current directory.")


if __name__ == '__main__':
    main()