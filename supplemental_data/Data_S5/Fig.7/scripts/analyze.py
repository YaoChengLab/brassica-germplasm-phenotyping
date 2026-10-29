"""Reproduce the archived fresh-weight models from accession-batch means.
Called by ../run_all.py. Inputs are local and never modified.
"""
import sys, os, json, numpy as np, pandas as pd
import statsmodels.formula.api as smf
from statsmodels.stats.outliers_influence import variance_inflation_factor
from scipy import stats

fw_path, pt_path, out = sys.argv[1:4]
os.makedirs(out, exist_ok=True)
logf = open(os.path.join(out, "fw_model_v2_log.txt"), "w", encoding="utf-8")
def P(*a):
    s = " ".join(str(x) for x in a); print(s); logf.write(s + "\n")

EXCL = [b for b in (sys.argv[4].split(",") if len(sys.argv) > 4 else []) if b]
TRAITS = ["area_ref", "count_ref", "solidity", "ellipse_aspect_ratio", "excess_green_index", "rgr_slope"]
ORDER = ["Pak choi", "Cauliflower", "Chinese kale", "Chinese cabbage", "Leaf mustard", "Cabbage", "Broccoli"]
PAL = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#F0E442"]
CELL_PX2 = 371.0 ** 2   # one 14.5 cm planting cell, ~25.6 px/cm (IMX219, 3.04 mm lens, 106 cm)

# Fresh-weight aggregation is archived in the input unit table (six significant digits).
# Plant-level image summaries are used only for batch diagnostics and input checks.
U = pd.read_csv(fw_path)
pt = pd.read_csv(pt_path)
assert not U.duplicated(["batch", "accession"]).any(), "Duplicate analysis units"
assert U[["fw_mean_g", "area_ref"]].gt(0).all().all(), "Nonpositive log input"
assert np.isfinite(U[TRAITS + ["fw_mean_g"]]).all().all(), "Missing or nonfinite model data"
assert (len(U), U.accession.nunique(), U.batch.nunique()) == (269, 257, 12)
U = U.sort_values(["batch", "accession"]).reset_index(drop=True)
U["in_model"] = ~U.batch.isin(EXCL)
U["exclusion_reason"] = np.where(U.in_model, "", "batch excluded from model")
U.to_csv(os.path.join(out, "Table_units_269.csv"), index=False, float_format="%.6g")
img = pt.groupby(["batch", "accession", "crop_type", "genome"]).agg(
    n_plants_img=("plant_id", "size"), das_ref=("das_ref", "first"),
    **{t: (t, "mean") for t in TRAITS}).reset_index()
joined = U.merge(img, on=["batch", "accession"], suffixes=("", "_plant"), validate="one_to_one")
assert len(joined) == len(U)
for t in TRAITS:
    assert np.allclose(joined[t], joined[t+"_plant"], rtol=6e-6, atol=1e-7), t
assert (joined.n_plants_img == joined.n_plants_img_plant).all()
lost = img.merge(U[["batch", "accession"]], on=["batch", "accession"], how="left", indicator=True)
lost = lost[lost._merge == "left_only"][["batch", "accession", "crop_type"]]
lost.to_csv(os.path.join(out, "Image_units_without_weight.csv"), index=False)
P(f"Archived dataset: {len(U)} units, {U.accession.nunique()} accessions, {U.batch.nunique()} batches")
P("Analysis starts from archived means; raw fresh-weight exclusions and means cannot be regenerated.")
P(f"Image units without archived fresh-weight means: {len(lost)}")
S = pd.crosstab(U.batch, U.crop_type).reindex(columns=ORDER)
S["units"] = S.sum(axis=1)
S["plants_img"] = U.groupby("batch").n_plants_img.sum()
S["plants_fw"] = U.groupby("batch").n_plants_fw.sum()
S.to_csv(os.path.join(out, "Table_units_summary_by_batch.csv"))

# ---------------- B12/B13 diagnostics ----------------
D = []
for b, g in U.groupby("batch"):
    p = pt[pt.batch == b]
    f = smf.ols("np.log(fw_mean_g) ~ np.log(area_ref)", g).fit()
    D.append(dict(batch=b, das_ref=g.das_ref.iloc[0], n_units=len(g), fw_median_g=g.fw_mean_g.median(),
                  area_median_px2=g.area_ref.median(),
                  fw_per_1e4px2=(g.fw_mean_g / g.area_ref * 1e4).median(),
                  rgr_median=p.rgr_slope.median(), count_median=g.count_ref.median(),
                  pct_plants_area_gt_cell=100 * (p.area_ref > CELL_PX2).mean(),
                  pearson_r_lnFW_lnArea=np.sign(f.params.iloc[1]) * np.sqrt(f.rsquared),
                  slope=f.params.iloc[1], R2=f.rsquared))
D = pd.DataFrame(D); D.to_csv(os.path.join(out, "Table_batch_diagnostics.csv"), index=False, float_format="%.4g")
P("\nBatch diagnostics:\n" + D.round(3).to_string(index=False))

# ---------------- model data ----------------
d = U[U.in_model].copy()
d["lnFW"] = np.log(d.fw_mean_g); d["lnArea"] = np.log(d.area_ref)
for t in ["count_ref", "solidity", "ellipse_aspect_ratio"]:
    d["z_" + t] = (d[t] - d[t].mean()) / d[t].std()
dup = d.accession.duplicated(keep=False)
P(f"\nModel set: {len(d)} units, {d.accession.nunique()} accessions ({d[dup].accession.nunique()} grown in >1 batch), "
  f"{d.batch.nunique()} batches, {d.crop_type.nunique()} crop groups; plants: img {d.n_plants_img.sum()}, FW {d.n_plants_fw.sum()}")

# association: batch-adjusted Pearson (ln FW vs trait; ln for area) + within-batch Spearman
P("\n=== Association with ln FW (batch-adjusted) ===")
A = []
res_fw = smf.ols("lnFW ~ C(batch)", d).fit().resid
for t in TRAITS:
    x = np.log(d[t]) if t == "area_ref" else d[t]
    rx = smf.ols("x ~ C(batch)", d.assign(x=x)).fit().resid
    r, p = stats.pearsonr(rx, res_fw)
    rb = d.groupby("batch")[[t, "fw_mean_g"]].rank()
    rs, ps = stats.spearmanr(rb[t], rb.fw_mean_g)
    A.append(dict(trait=t, partial_pearson_r=r, p=p, within_batch_spearman_rho=rs, p_spearman=ps))
A = pd.DataFrame(A); A["p_bonferroni"] = np.minimum(A.p * len(A), 1)
A.to_csv(os.path.join(out, "Table_association.csv"), index=False, float_format="%.4g")
P(A.round(4).to_string(index=False))

# models
F = {"M0": "lnFW ~ C(batch)",
     "M1": "lnFW ~ lnArea + C(batch)",
     "M2": "lnFW ~ lnArea + z_count_ref + z_solidity + C(batch)",
     "M2_aspect": "lnFW ~ lnArea + z_count_ref + z_ellipse_aspect_ratio + C(batch)"}
grp = pd.factorize(d.accession)[0]
fit = {k: smf.ols(f, d).fit() for k, f in F.items()}
fitc = {k: smf.ols(f, d).fit(cov_type="cluster", cov_kwds={"groups": grp}) for k, f in F.items()}

fold_records = []
repeat_records = []
def cv_pred(formula, d, k=10, seed=0):
    rng = np.random.default_rng(seed); acc = np.array(sorted(d.accession.unique())); rng.shuffle(acc)
    fo = d.accession.map({a: i % k for i, a in enumerate(acc)}).values
    if formula == F["M0"]:
        fold_records.extend(dict(repeat=seed, batch=b, accession=a, fold=int(f))
                            for b, a, f in zip(d.batch, d.accession, fo))
    pred = np.full(len(d), np.nan)
    for i in range(k):
        tr = fo != i
        assert set(d.loc[tr, "accession"]).isdisjoint(set(d.loc[~tr, "accession"]))
        assert set(d.loc[~tr, "batch"]).issubset(set(d.loc[tr, "batch"]))
        pred[~tr] = smf.ols(formula, d[tr]).fit().predict(d[~tr])
    return pred

REP = 50
cvs = {}
for k, f in F.items():
    r2, rm, preds = [], [], []
    for s in range(REP):
        pr = cv_pred(f, d, seed=s); res = d.lnFW.values - pr
        r2.append(1 - (res ** 2).sum() / ((d.lnFW - d.lnFW.mean()) ** 2).sum()); rm.append(np.sqrt((res ** 2).mean()))
        preds.append(pr)
        repeat_records.append(dict(model=k, repeat=s, R2=r2[-1], RMSE_ln=rm[-1]))
    cvs[k] = dict(r2=np.mean(r2), r2_sd=np.std(r2), rmse=np.mean(rm), rmse_sd=np.std(rm), pred=np.mean(preds, axis=0))

rows = []
for k in F:
    f = fit[k]
    rows.append(dict(model=k, formula=F[k], n=int(f.nobs), params=int(f.df_model) + 1, R2=f.rsquared,
                     adj_R2=f.rsquared_adj, AIC=f.aic, BIC=f.bic, RMSE_ln=np.sqrt(f.mse_resid),
                     CV_R2=cvs[k]["r2"], CV_R2_sd=cvs[k]["r2_sd"], CV_RMSE_ln=cvs[k]["rmse"], CV_RMSE_sd=cvs[k]["rmse_sd"],
                     CV_median_abs_pct_err=100 * np.median(np.abs(np.exp(d.lnFW - cvs[k]["pred"]) - 1))))
M = pd.DataFrame(rows); M.to_csv(os.path.join(out, "Table_model_comparison.csv"), index=False, float_format="%.4g")
P("\n=== Models ===\n" + M.drop(columns="formula").round(4).to_string(index=False))
pr2 = lambda a, b: (fit[b].ssr - fit[a].ssr) / fit[b].ssr
P(f"\nPartial R2: area|batch={pr2('M1','M0'):.4f}; count+solidity|area,batch={pr2('M2','M1'):.4f}; "
  f"count+aspect|area,batch={pr2('M2_aspect','M1'):.4f}")
for big in ["M2", "M2_aspect"]:
    Fv, pv, df = fit[big].compare_f_test(fit["M1"])
    P(f"Nested F {big} vs M1: F(2,{int(fit[big].df_resid)})={Fv:.3f}, p={pv:.3g}")
    # cluster-robust Wald
    w = fitc[big].wald_test([n for n in fitc[big].params.index if n.startswith("z_")], scalar=True)
    P(f"  cluster-robust Wald: chi2={float(w.statistic):.3f}, p={float(w.pvalue):.3g}")

coef = []
for k in ["M1", "M2", "M2_aspect"]:
    fr = fitc[k]; ci = fr.conf_int()
    for n in fr.params.index:
        if n.startswith("C(batch"): continue
        coef.append(dict(model=k, term=n, coef=fr.params[n], SE_cluster=fr.bse[n], CI95_lo=ci.loc[n, 0],
                         CI95_hi=ci.loc[n, 1], p=fr.pvalues[n]))
Ctab = pd.DataFrame(coef); Ctab.to_csv(os.path.join(out, "Table_coefficients.csv"), index=False, float_format="%.4g")
P("\nCoefficients (cluster-robust SE by accession):\n" + Ctab.round(4).to_string(index=False))

X = d[["lnArea", "z_count_ref", "z_solidity"]].assign(c=1).values
P("VIF (lnArea, count, solidity):", [round(variance_inflation_factor(X, i), 2) for i in range(3)])
# within-batch Pearson r of ln area for figure
r_w, p_w = A.loc[A.trait == "area_ref", ["partial_pearson_r", "p"]].values[0]

# residual diagnostics
P("Shapiro-Wilk on M1 residuals: W=%.3f p=%.3g" % stats.shapiro(fit["M1"].resid))
P("Breusch-Pagan M1: p=%.3g" % __import__("statsmodels.stats.diagnostic", fromlist=["x"]).het_breuschpagan(
    fit["M1"].resid, fit["M1"].model.exog)[1])
infl = fit["M1"].get_influence().cooks_distance[0]
P(f"Max Cook's D M1 = {infl.max():.3f} ({d.iloc[infl.argmax()][['batch','accession']].tolist()})")

# sensitivity: crop group added
fr = smf.ols("lnFW ~ lnArea + C(batch) + C(crop_type)", d).fit(cov_type="cluster", cov_kwds={"groups": grp})
P(f"Sensitivity M1 + crop group: lnArea={fr.params.lnArea:.3f} (SE {fr.bse.lnArea:.3f}); adjR2={fr.rsquared_adj:.4f}")

# ---------------- figure ----------------
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
plt.rcParams.update({"font.sans-serif": ["Arial", "Liberation Sans", "DejaVu Sans"], "font.size": 8,
                     "axes.unicode_minus": False, "pdf.fonttype": 42, "svg.fonttype": "none",
                     "mathtext.fontset": "custom", "mathtext.rm": "Arial", "savefig.facecolor": "white"})
def style(ax):
    ax.grid(color="#e6e6e6", lw=0.6); ax.set_axisbelow(True)
    for s in ("top", "right"): ax.spines[s].set_visible(False)
    for s in ("left", "bottom"): ax.spines[s].set_color("#9a9a9a"); ax.spines[s].set_linewidth(0.8)
    ax.tick_params(length=2.5, color="#9a9a9a")
col = dict(zip(ORDER, PAL))
fig, ax = plt.subplots(1, 2, figsize=(180 / 25.4, 82 / 25.4))
# (a) batch-adjusted ln FW vs ln area
gx = d.lnArea - d.groupby("batch").lnArea.transform("mean") + d.lnArea.mean()
gy = d.lnFW - d.groupby("batch").lnFW.transform("mean") + d.lnFW.mean()
for c in ORDER:
    m = d.crop_type == c
    ax[0].scatter(gx[m], gy[m], s=11, color=col[c], edgecolor="#555555" if c == "Broccoli" else "none",
                  lw=0.3, alpha=.9, label=f"{c} ({m.sum()})")
b = fit["M1"].params.lnArea
xs = np.linspace(gx.min(), gx.max(), 50)
ax[0].plot(xs, gy.mean() + b * (xs - gx.mean()), color="black", lw=1)
lo, hi = fitc["M1"].conf_int().loc["lnArea"]
ax[0].text(.03, .97, f"$r$ = {r_w:.2f}, $p$ < 0.001\nslope = {b:.2f} (95% CI {lo:.2f}–{hi:.2f})\n$n$ = {len(d)} accessions × batch",
           transform=ax[0].transAxes, va="top", fontsize=7)
ax[0].set_xlabel("ln projected leaf area (px$^2$), batch-adjusted")
ax[0].set_ylabel("ln fresh weight (g), batch-adjusted")
ax[0].legend(fontsize=6, frameon=False, loc="lower right", handletextpad=.2, borderaxespad=.2)
style(ax[0])
# (b) observed vs cross-validated predicted FW, area model
pred = np.exp(cvs["M1"]["pred"])
for c in ORDER:
    m = (d.crop_type == c).values
    ax[1].scatter(pred[m], d.fw_mean_g.values[m], s=11, color=col[c],
                  edgecolor="#555555" if c == "Broccoli" else "none", lw=0.3, alpha=.9)
lim = [min(pred.min(), d.fw_mean_g.min()) * .8, max(pred.max(), d.fw_mean_g.max()) * 1.2]
ax[1].plot(lim, lim, "--", color="#555555", lw=.8)
ax[1].set_xscale("log"); ax[1].set_yscale("log"); ax[1].set_xlim(lim); ax[1].set_ylim(lim)
ax[1].set_xlabel("Predicted fresh weight (g), cross-validated"); ax[1].set_ylabel("Observed fresh weight (g)")
m1, m2 = M.set_index("model").loc["M1"], M.set_index("model").loc["M2"]
Fv, pv, _ = fit["M2"].compare_f_test(fit["M1"])
ax[1].text(.03, .97,
           f"Batch only: CV $R^2$ = {M.set_index('model').loc['M0'].CV_R2:.3f}\n"
           f"+ PLA: CV $R^2$ = {m1.CV_R2:.3f}\n"
           f"+ leaf count, solidity: CV $R^2$ = {m2.CV_R2:.3f}\n"
           f"added terms: $F$$_{{2,{int(fit['M2'].df_resid)}}}$ = {Fv:.2f}, $p$ = {pv:.3f}",
           transform=ax[1].transAxes, va="top", ha="left", fontsize=6.5, linespacing=1.3)
from matplotlib.ticker import FixedLocator, FixedFormatter
for axis in (ax[1].xaxis, ax[1].yaxis):
    axis.set_major_locator(FixedLocator([1, 3, 10, 30, 100])); axis.set_major_formatter(FixedFormatter(["1", "3", "10", "30", "100"]))
style(ax[1])
for a, l in zip(ax, "ab"):
    a.text(-0.16, 1.02, f"({l})", transform=a.transAxes, fontsize=10, fontweight="bold", va="bottom")
plt.tight_layout()
for ext in ("png", "pdf", "svg"):
    plt.savefig(os.path.join(out, f"Fig7.{ext}"), dpi=600 if ext == "png" else None)
logf.close()

# sensitivity: also exclude 2025B11 (7-day harvest gap; weak within-batch fit)
dd = d[d.batch != "2025B11"].copy()
f1, f2 = smf.ols(F["M1"], dd).fit(), smf.ols(F["M2"], dd).fit()
Fv, pv, _ = f2.compare_f_test(f1)
logf = open(os.path.join(out, "fw_model_v2_log.txt"), "a", encoding="utf-8")
P(f"\nSensitivity without 2025B11: n={len(dd)}; M1 slope={f1.params.lnArea:.3f}, adjR2 M1={f1.rsquared_adj:.4f}, "
  f"M2={f2.rsquared_adj:.4f}; F test M2 vs M1 F={Fv:.3f} p={pv:.3g}")
logf.close()

# Machine-readable checks and summaries; all values are recalculated, not copied.
from statsmodels.stats.diagnostic import het_breuschpagan
from pathlib import Path
outpath = Path(out)
pd.DataFrame(fold_records).to_csv(outpath / 'CV_folds.csv', index=False)
pd.DataFrame(repeat_records).to_csv(outpath / 'CV_repeat_metrics.csv', index=False)
M.to_csv(outpath / 'Model_statistics_full_precision.csv', index=False)
Ctab.to_csv(outpath / 'Coefficients_full_precision.csv', index=False)
A.to_csv(outpath / 'Associations_full_precision.csv', index=False)
D.to_csv(outpath / 'Batch_diagnostics_full_precision.csv', index=False)
coords = d[['batch', 'accession', 'crop_type', 'fw_mean_g', 'area_ref']].copy()
coords['panel_a_x'] = gx
coords['panel_a_y'] = gy
for key in cvs:
    coords[key + '_mean_pred_lnFW'] = cvs[key]['pred']
coords['panel_b_predicted_g'] = np.exp(cvs['M1']['pred'])
coords.to_csv(outpath / 'Figure7_plot_data.csv', index=False)

r = float(r_w)
se_z = 1 / np.sqrt(len(d) - d.batch.nunique() - 2)
rlo, rhi = np.tanh(np.arctanh(r) + np.array([-1, 1]) * 1.96 * se_z)
f2, pf2, df2 = fit['M2'].compare_f_test(fit['M1'])
w = fitc['M2'].wald_test(['z_count_ref', 'z_solidity'], scalar=True)
interaction = smf.ols('lnFW ~ lnArea * C(batch)', d).fit()
fh, ph, dfh = interaction.compare_f_test(fit['M1'])
shapiro = stats.shapiro(fit['M1'].resid)
bp = het_breuschpagan(fit['M1'].resid, fit['M1'].model.exog)
vifs = [float(variance_inflation_factor(X, i)) for i in range(3)]
summary = {
    'n_units':len(d), 'n_accessions':int(d.accession.nunique()), 'n_batches':int(d.batch.nunique()),
    'n_plants_imaged':int(d.n_plants_img.sum()), 'n_plants_weighed':int(d.n_plants_fw.sum()),
    'partial_r':r, 'partial_r_CI95':[float(rlo), float(rhi)],
    'correlation_CI_method':'Approximate Fisher z interval, adjusted for batch covariates; not cluster-robust',
    'slope':float(fit['M1'].params.lnArea),
    'slope_CI95':fitc['M1'].conf_int().loc['lnArea'].tolist(),
    'nested_F':float(f2), 'nested_F_df':[float(df2),float(fit['M2'].df_resid)], 'nested_F_p':float(pf2),
    'clustered_Wald_chi2':float(w.statistic), 'clustered_Wald_df':2, 'clustered_Wald_p':float(w.pvalue),
    'interaction_F':float(fh), 'interaction_df':[float(dfh),float(interaction.df_resid)], 'interaction_p':float(ph),
    'CV':{k:{a:float(v) for a,v in z.items() if a!='pred'} for k,z in cvs.items()},
    'Shapiro_W':float(shapiro.statistic), 'Shapiro_p':float(shapiro.pvalue),
    'Breusch_Pagan_LM':float(bp[0]), 'Breusch_Pagan_p':float(bp[1]),
    'VIF':dict(zip(['lnArea','leaf_count','solidity'],vifs)),
    'max_Cooks_D':float(infl.max()),
    'max_Cooks_unit':d.iloc[infl.argmax()][['batch','accession']].tolist(),
    'area_partial_R2_given_batch':float(pr2('M1','M0')),
    'crop_group_sensitivity':{'area_slope':float(fr.params.lnArea), 'clustered_SE':float(fr.bse.lnArea), 'adjusted_R2':float(fr.rsquared_adj)},
    'without_B11_sensitivity':{'n_units':len(dd),'area_slope':float(f1.params.lnArea),'extended_F_p':float(pv)},
}
(outpath / 'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False)+'\n', encoding='utf-8')
checks = [
 ['M2 vs M1', 'nested F', float(f2),float(pf2)],
 ['M2 vs M1', 'accession-clustered Wald chi-square',float(w.statistic),float(w.pvalue)],
 ['batch × lnArea', 'nested F',float(fh),float(ph)],
 ['M1 residuals','Shapiro-Wilk',float(shapiro.statistic),float(shapiro.pvalue)],
 ['M1 residuals','Breusch-Pagan LM',float(bp[0]),float(bp[1])],
]
pd.DataFrame(checks,columns=['comparison','test','statistic','p']).to_csv(outpath/'Model_checks.csv',index=False)
res = d[['batch','accession','crop_type','lnFW','lnArea']].copy()
res['fitted_lnFW'] = fit['M1'].fittedvalues
res['residual_lnFW'] = fit['M1'].resid
influence = fit['M1'].get_influence()
res['studentized_residual'] = influence.resid_studentized_internal
res['leverage'] = influence.hat_matrix_diag
res['Cooks_D'] = infl
res.to_csv(outpath/'Residuals_and_influence.csv',index=False)
from plot_checks import plot_checks
plot_checks(outpath)
