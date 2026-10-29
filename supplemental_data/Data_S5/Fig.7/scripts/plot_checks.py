"""Plot model diagnostics from the exported residual data."""
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def plot_checks(out):
    out=Path(out);res=pd.read_csv(out/'Residuals_and_influence.csv')
    fig,axs=plt.subplots(2,2,figsize=(9,7))
    axs[0,0].scatter(res.fitted_lnFW,res.residual_lnFW,s=14,alpha=.7)
    axs[0,0].axhline(0,color='black',lw=.7)
    axs[0,0].set(xlabel='Fitted ln fresh weight',ylabel='Residual (ln scale)',title='Residuals versus fitted values')
    stats.probplot(res.residual_lnFW,dist='norm',plot=axs[0,1]);axs[0,1].set_title('Normal Q–Q plot')
    axs[1,0].scatter(res.leverage,res.studentized_residual,s=14,alpha=.7)
    axs[1,0].axhline(0,color='black',lw=.7)
    axs[1,0].set(xlabel='Leverage',ylabel='Studentized residual',title='Residuals versus leverage')
    axs[1,1].stem(np.arange(len(res)),res.Cooks_D,markerfmt=' ',basefmt=' ')
    i=int(res.Cooks_D.argmax());label=res.iloc[i]['batch']+' / '+res.iloc[i]['accession']
    axs[1,1].annotate(label,(i,res.Cooks_D.iloc[i]),xytext=(-110,-25),textcoords='offset points',fontsize=8,
                      arrowprops={'arrowstyle':'-','color':'gray','lw':.6})
    axs[1,1].set(xlabel='Analysis-unit index (batch, accession order)',ylabel="Cook's distance",title='Influence on area-model fit')
    fig.tight_layout();fig.savefig(out/'Model_checks.png',dpi=180);fig.savefig(out/'Model_checks.pdf');plt.close(fig)

if __name__=='__main__':
    import sys
    plot_checks(sys.argv[1])
