1.     f.write(f'Interaction features AUC: {auc_inter:.4f}' + chr(92) + 'n')
2.     f.write(f'AUC improvement: {auc_improvement:.4f}' + chr(92) + 'n')
3.     f.write(f'Improvement threshold: {improvement_threshold:.2f}' + chr(92) + 'n')
4.     f.write(f'Hypothesis supported (improvement > 0.05): {hypothesis_supported}' + chr(92) + 'n')
