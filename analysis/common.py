"""Shared paths and process constants for the PRSG analysis scripts."""
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Original repository paths are kept as they are (they are linked from elsewhere).
TAPEOUT_DIR = REPO / "12_ELEC4609_FALL2022"          # submission package (group 12)
GDS = TAPEOUT_DIR / "12_ELEC4609_FALL2022.gds"
LVS_REPORT = TAPEOUT_DIR / "top_layout_langsun.lvs.report"
DRC_SUMMARY = TAPEOUT_DIR / "top_layout_langsun.drc.summary"
DIE_PHOTO = REPO / "G12C1.jpg"
SCOPE_DIR = REPO / "post_fab_test"
IMG_DIR = REPO / "docs" / "img"
RESULTS_DIR = REPO / "analysis" / "results"

TOP_CELL = "top_layout_langsun"

# Carleton University SOI PDK ("CuSOiPDk"), scalable lambda rules.
# Every coordinate in the GDS sits on a 2.4 um grid and the frame is 240 lambda
# tall (576 um), so lambda = 2.4 um.
LAMBDA_UM = 2.4

# GDS layer -> PDK layer name. The GDS carries no names; this mapping was
# recovered by matching per-layer polygon counts against the Calibre DRC summary
# (e.g. METAL 258 (908) == layer 5: 258 hierarchical / 908 flat shapes), and by
# geometry: layer 2 lies entirely inside layer 4 and covers every PMOS gate,
# so 2 = Pplus and 4 = NWELL. Datatype 999 on layers 1/5/7 is the ART layer
# (45 shapes, matching "LAYER ART ... 45").
LAYERS = {
    "DWELL": (1, 0),     # silicon island / active area
    "PPLUS": (2, 0),
    "NWELL": (4, 0),
    "METAL": (5, 0),     # the only metal layer
    "CONTACT": (6, 0),
    "POLY": (7, 0),
}
ART_DATATYPE = 999
PAD_TEXT = (230, 0)      # pad names in the frame cell


def rel(path):
    """Repository-relative path for headers and messages."""
    return Path(path).resolve().relative_to(REPO).as_posix()


def ensure_dirs():
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
