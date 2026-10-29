"""Shared plotting settings for the manuscript figures.

Every plotting script in this folder imports from here, so fonts, axis styling and the
colors of the three leaf selections are defined once.
"""
import matplotlib.pyplot as plt

RCPARAMS = {
    "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
    "font.size": 8,
    "axes.unicode_minus": False,
    "pdf.fonttype": 42,      # embed TrueType, not Type 3 (journal requirement)
    "ps.fonttype": 42,
    "svg.fonttype": "none",  # SVG keeps text as editable text (for Illustrator), not glyph paths
    "mathtext.fontset": "custom",   # superscripts in units (10$^3$ px$^2$) in Arial too, not DejaVu
    "mathtext.rm": "Arial",
    "mathtext.it": "Arial:italic",
    "mathtext.bf": "Arial:bold",
    "savefig.facecolor": "white",
}
FORMATS = ("png", "pdf", "svg")
plt.rcParams.update(RCPARAMS)

GRID = "#e6e6e6"
XLABEL_DAS = "Days after sowing (DAS)"

# The three leaf selections of Figure 5 and Figure S3: the same detected
# polygons with all detections (raw), those kept by automatic ownership assignment
# (auto) and those kept after manual review (qc). Colors are checked for color-vision
# deficiency; the labels are used verbatim in every figure.
SELECTIONS = ("raw", "auto", "qc")
SEL_COLOR = {"raw": "#009E73", "auto": "#0B6BCB", "qc": "#D55E00"}
SEL_LABEL = {"raw": "Segmentation", "auto": "+ Ownership", "qc": "+ Manual review"}
LS_REVIEW = (0, (0.1, 2))    # manual review is drawn as a round-dotted line


def style(ax):
    """Light grid, no top/right spines, gray axes."""
    ax.grid(color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#9a9a9a")
        ax.spines[s].set_linewidth(0.8)
    ax.tick_params(length=2.5, color="#9a9a9a")
