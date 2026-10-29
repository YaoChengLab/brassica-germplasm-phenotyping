# Full statistics retained separately from Table S7.

- All: all 12 batches. Exclude: models exclude 2025B12 and 2025B13.

- M0: batch only. M1: projected leaf area + batch. M2: M1 + leaf count + solidity.

- M2_aspect replaces solidity with aspect ratio. Response and area use natural logarithms.

- CV R² and RMSE are calculated on the ln(fresh weight) scale. SD uses ddof=0, as in the original script.

The clustered Wald statistic is chi-square (2 df), not F. Coefficient and slope intervals use clustered standard errors.

The correlation interval uses an approximate Fisher z calculation adjusted for batch covariates; it is not cluster-robust.

