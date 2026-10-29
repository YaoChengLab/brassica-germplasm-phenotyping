"""Create the seven-row Table S7 and separate full model details."""
from pathlib import Path
import json,sys,subprocess
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font,PatternFill,Alignment,Border,Side
from openpyxl.utils import get_column_letter
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

out=Path(sys.argv[1]);root=Path(__file__).resolve().parents[1]
a=json.loads((out/'all_batches/summary.json').read_text(encoding='utf-8'))
b=json.loads((out/'without_B12_B13/summary.json').read_text(encoding='utf-8'))
header=['Measure','All 12 batches','Without 2025B12 and 2025B13']
def cells(s):
    lo,hi=s['partial_r_CI95']
    return [s['n_units'],s['n_accessions'],f"{s['partial_r']:.2f} ({lo:.2f}–{hi:.2f})",
            f"{s['CV']['M1']['r2']:.3f} ± {s['CV']['M1']['r2_sd']:.3f}",
            f"{s['CV']['M2']['r2']:.3f} ± {s['CV']['M2']['r2_sd']:.3f}",
            f"{s['nested_F_p']:.3f}",f"{s['clustered_Wald_p']:.3f}"]
labels=['Accession–batch units','Accessions','Batch-adjusted correlation, r (95% CI)',
        'Area model: cross-validated R²','Extended model: cross-validated R²',
        'Added traits: F-test p-value','Added traits: clustered Wald p-value']
rows=list(map(list,zip(labels,cells(a),cells(b))))
title='Table S7. Fresh-weight model comparison.'
notes=[
'Each analysis unit is an accession mean within a batch. The second analysis contains 10 batches.',
'Area model: ln(fresh weight) ~ ln(projected leaf area) + batch.',
'Extended model: area model + standardized leaf count + standardized solidity.',
'Cross-validated R²: mean ± SD across 50 repetitions of 10-fold cross-validation. All records from an accession stay in the same fold.',
'The correlation uses log-transformed fresh weight and projected leaf area after adjustment for batch. Its 95% CI uses the Fisher z approximation.',
'The F and Wald tests compare the extended model with the area model. The Wald test uses standard errors clustered by accession.',
'Full model statistics, residual checks and sensitivity analyses are supplied separately in Model_details.xlsx.'
]
pd.DataFrame(rows,columns=header).to_csv(out/'Table_S7.csv',index=False)
(out/'Table_S7_notes.txt').write_text(title+'\n\n'+'\n'.join(notes)+'\n',encoding='utf-8')
wb=Workbook();ws=wb.active;ws.title='S7'
ws.merge_cells('A1:C2');ws['A1']=title
ws['A1'].font=Font(name='Arial',size=13,bold=True,color='16324F');ws['A1'].alignment=Alignment(wrap_text=True,vertical='center')
for i,h in enumerate(header,1): ws.cell(4,i,h)
for row in rows: ws.append(row)
for row in ws.iter_rows(min_row=4,max_row=11,max_col=3):
    for c in row:
        c.font=Font(name='Arial',size=11,bold=c.row==4,color='FFFFFF' if c.row==4 else '1F2937')
        c.fill=PatternFill('solid',fgColor='24476A' if c.row==4 else ('EEF3F7' if c.row%2 else 'FFFFFF'))
        c.alignment=Alignment(horizontal='left' if c.column==1 else 'center',vertical='center',wrap_text=True)
        c.border=Border(bottom=Side(style='thin',color='D5DFE8'))
for i,note in enumerate(notes,14):
    ws.merge_cells(start_row=i,start_column=1,end_row=i,end_column=3);ws.cell(i,1,note)
    ws.cell(i,1).font=Font(name='Arial',size=10,color='475569');ws.cell(i,1).alignment=Alignment(wrap_text=True,vertical='top')
    ws.row_dimensions[i].height=32 if len(note)>125 else 27
for c,w in [('A',51),('B',27),('C',35)]: ws.column_dimensions[c].width=w
ws.row_dimensions[1].height=22;ws.row_dimensions[2].height=20;ws.row_dimensions[4].height=34
for i in range(5,12): ws.row_dimensions[i].height=29
ws.freeze_panes='B5';ws.sheet_view.showGridLines=False
ws.print_options.horizontalCentered=True;ws.sheet_properties.pageSetUpPr.fitToPage=True
ws.page_setup.orientation='landscape';ws.page_setup.paperSize=ws.PAPERSIZE_A4;ws.page_setup.fitToWidth=1;ws.page_setup.fitToHeight=1
ws.print_area='A1:C20';wb.save(out/'Table_S7.xlsx')

# Keep all original statistics in a detailed companion, outside the concise S7.
subprocess.run([sys.executable,str(root/'scripts/make_details.py'),str(out/'all_batches'),str(out/'without_B12_B13'),str(out/'Detailed_model_statistics.csv')],check=True,stdout=subprocess.DEVNULL)
details=Workbook();details.remove(details.active)
for case,prefix in [('all_batches','All'),('without_B12_B13','Exclude')]:
    for filename,short in [('Model_statistics_full_precision.csv','models'),('Coefficients_full_precision.csv','coefficients'),('Associations_full_precision.csv','associations'),('Model_checks.csv','checks'),('Batch_diagnostics_full_precision.csv','batch_fits'),('CV_repeat_metrics.csv','CV_metrics')]:
        if short=='batch_fits' and prefix=='Exclude':continue
        df=pd.read_csv(out/case/filename).fillna('')
        sheet=details.create_sheet(prefix+'_'+short);sheet.append(df.columns.tolist())
        for row in df.itertuples(index=False,name=None):sheet.append(row)
        sheet.freeze_panes='A2';sheet.auto_filter.ref=sheet.dimensions
        for cell in sheet[1]:cell.font=Font(bold=True,color='FFFFFF');cell.fill=PatternFill('solid',fgColor='24476A');cell.alignment=Alignment(wrap_text=True)
        for i,col in enumerate(df.columns,1):sheet.column_dimensions[get_column_letter(i)].width=min(48,max(16,len(col)+2))
sheet=details.create_sheet('Original_S7_statistics',0)
df=pd.read_csv(out/'Detailed_model_statistics.csv').fillna('');sheet.append(df.columns.tolist())
for row in df.itertuples(index=False,name=None):sheet.append(row)
for c,w in [('A',62),('B',36),('C',42)]:sheet.column_dimensions[c].width=w
sheet.freeze_panes='B2';sheet.row_dimensions[1].height=32
for c in sheet[1]:c.font=Font(bold=True);c.alignment=Alignment(wrap_text=True)
notesheet=details.create_sheet('Read_me',0)
for line in [
 'Full statistics retained separately from the concise Table S7.',
 'All: all 12 batches. Exclude: models exclude 2025B12 and 2025B13.',
 'M0: batch only. M1: projected leaf area + batch. M2: M1 + leaf count + solidity.',
 'M2_aspect replaces solidity with aspect ratio. Response and area use natural logarithms.',
 'CV R² and RMSE are calculated on the ln(fresh weight) scale. SD uses ddof=0, as in the original script.',
 'The clustered Wald statistic is chi-square (2 df), not F. Coefficient and slope intervals use clustered standard errors.',
 'The correlation interval uses an approximate Fisher z calculation adjusted for batch covariates; it is not cluster-robust.',
 'Original_S7_statistics preserves the earlier calculation, including rounded intermediate exports.',
 'CV_median_abs_pct_err preserves the legacy formula: 100 × median(abs(observed/predicted - 1)); denominator is predicted weight.',
 'Batch diagnostics are descriptive; the 371² px² cell threshold is inherited and does not establish physical calibration.',
 'Residual plots, influence rows, fold assignments and sensitivity summaries are in the scenario folders.',
]:notesheet.append([line])
notesheet.column_dimensions['A'].width=120
for row in notesheet:
 row[0].alignment=Alignment(wrap_text=True,vertical='top');notesheet.row_dimensions[row[0].row].height=30
details.save(out/'Model_details.xlsx')

fig,ax=plt.subplots(figsize=(11.7,7.5));ax.axis('off')
ax.text(0,1.01,title,fontsize=13,weight='bold',transform=ax.transAxes)
tab=ax.table(cellText=rows,colLabels=['Measure','All 12 batches','Without 2025B12\nand 2025B13'],colWidths=[.47,.24,.29],cellLoc='left',bbox=[0,.43,1,.53])
tab.auto_set_font_size(False);tab.set_fontsize(10)
for (r,c),cell in tab.get_celld().items():
 cell.set_edgecolor('#D5DFE8')
 if r==0:cell.set_facecolor('#24476A');cell.get_text().set_color('white');cell.get_text().set_weight('bold')
 elif r%2:cell.set_facecolor('#EEF3F7')
 if c>0:cell.get_text().set_ha('center')
import textwrap
ax.text(0,.38,'\n\n'.join(textwrap.fill(x,150) for x in notes),fontsize=8.5,va='top',transform=ax.transAxes)
fig.savefig(out/'Table_S7_preview.png',dpi=160,bbox_inches='tight');plt.close(fig)
