"""Supplementary table: model statistics with all 12 batches vs excluding 2025B12/2025B13.
Usage: python som_compare.py <out_all dir> <out_excl dir> <out csv>"""
import sys, pandas as pd, numpy as np, statsmodels.formula.api as smf
def summarize(dirn, excl):
    u = pd.read_csv(f'{dirn}/Table_units_269.csv'); d = u[~u.batch.isin(excl)].copy()
    d['lnFW'] = np.log(d.fw_mean_g); d['lnA'] = np.log(d.area_ref)
    M = pd.read_csv(f'{dirn}/Table_model_comparison.csv').set_index('model')
    Cf = pd.read_csv(f'{dirn}/Table_coefficients.csv'); As = pd.read_csv(f'{dirn}/Table_association.csv').set_index('trait')
    g = pd.factorize(d.accession)[0]
    a = smf.ols('lnFW ~ lnA + C(batch)', d).fit(); b = smf.ols('lnFW ~ lnA * C(batch)', d).fit()
    Fh, ph, dfh = b.compare_f_test(a)
    m0 = smf.ols('lnFW ~ C(batch)', d).fit()
    d['zc'] = (d.count_ref - d.count_ref.mean()) / d.count_ref.std(); d['zs'] = (d.solidity - d.solidity.mean()) / d.solidity.std()
    m2 = smf.ols('lnFW ~ lnA + zc + zs + C(batch)', d).fit(); F2, p2, _ = m2.compare_f_test(a)
    w = smf.ols('lnFW ~ lnA + zc + zs + C(batch)', d).fit(cov_type='cluster', cov_kwds={'groups': g}).wald_test(['zc', 'zs'], scalar=True)
    cf = lambda mod, t: Cf[(Cf.model == mod) & (Cf.term == t)].iloc[0]
    s1 = cf('M1', 'lnArea')
    r = As.loc['area_ref', 'partial_pearson_r']; n = len(d); z = np.arctanh(r); se = 1 / np.sqrt(n - d.batch.nunique() - 2)
    cook = a.get_influence().cooks_distance[0]
    fp = lambda p: f'{p:.1e}' if p < 0.001 else f'{p:.3f}'
    return {
     'Analysis units (accession × batch)': f'{n}',
     'Accessions / batches': f'{d.accession.nunique()} / {d.batch.nunique()}',
     'Plants imaged / weighed': f'{int(d.n_plants_img.sum())} / {int(d.n_plants_fw.sum())}',
     'Partial r, ln PLA vs ln FW (95% CI)': f'{r:.2f} ({np.tanh(z-1.96*se):.2f}–{np.tanh(z+1.96*se):.2f})',
     'Within-batch Spearman rho, PLA vs FW': f"{As.loc['area_ref','within_batch_spearman_rho']:.2f}",
     'Slope of ln FW on ln PLA, M1 (95% CI)': f"{s1.coef:.2f} ({s1.CI95_lo:.2f}–{s1.CI95_hi:.2f})",
     'Partial R² of ln PLA after batch': f'{(m0.ssr-a.ssr)/m0.ssr:.2f}',
     'M1 adjusted R²': f"{M.loc['M1','adj_R2']:.3f}",
     'M1 cross-validated R² (mean ± SD, 50 repeats)': f"{M.loc['M1','CV_R2']:.3f} ± {M.loc['M1','CV_R2_sd']:.3f}",
     'M1 cross-validated RMSE (ln scale)': f"{M.loc['M1','CV_RMSE_ln']:.3f}",
     'M1 median absolute prediction error': f"{M.loc['M1','CV_median_abs_pct_err']:.0f}%",
     'M2 cross-validated R² (mean ± SD)': f"{M.loc['M2','CV_R2']:.3f} ± {M.loc['M2','CV_R2_sd']:.3f}",
     'ΔAIC, M2 − M1': f"{M.loc['M2','AIC']-M.loc['M1','AIC']:+.1f}",
     'ΔBIC, M2 − M1': f"{M.loc['M2','BIC']-M.loc['M1','BIC']:+.1f}",
     'M2 vs M1, nested F test': f'F(2,{int(m2.df_resid)}) = {F2:.2f}, P = {fp(p2)}',
     'M2 vs M1, cluster-robust Wald test, P': f'{fp(float(w.pvalue))}',
     'Leaf count coefficient in M2, P': f"{cf('M2','z_count_ref').p:.2f}",
     'Solidity coefficient in M2, P': f"{cf('M2','z_solidity').p:.3f}",
     'Batch × ln PLA interaction (slope heterogeneity)': f'F({int(dfh)},{int(b.df_resid)}) = {Fh:.2f}, P = {fp(ph)}',
     "Largest Cook's distance, M1 (unit)": f"{cook.max():.2f} ({d.iloc[cook.argmax()].batch} {d.iloc[cook.argmax()].accession})",
    }
T = pd.DataFrame({'All 12 batches (main analysis)': summarize(sys.argv[1], []),
                  'Excluding 2025B12 and 2025B13 (sensitivity)': summarize(sys.argv[2], ['2025B12', '2025B13'])})
T.index.name = 'Statistic'; T.to_csv(sys.argv[3]); print(T.to_string())
