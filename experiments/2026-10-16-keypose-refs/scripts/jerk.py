"""Quick smoothness check (spine_qa's measure) for chosen bones of one animation: worst frames."""
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "plugin/skills/skipbo-art/scripts"))
import spine_qa as q  # noqa: E402
r = q.Rig(Path(sys.argv[1])); an = sys.argv[2]; H = r.data["skeleton"]["height"]
n = int(round(r.duration(an) * 30)) + 1
for b in sys.argv[3:]:
    P = np.array([r.pose(an, i / 30)[0][b] for i in range(n)])
    jp = np.linalg.norm(np.diff(np.diff(P[:, 4:6], axis=0) / H, axis=0), axis=1)
    i = int(np.argmax(jp)); print(b, "worst pos", round(float(jp[i]), 4), "at", i + 1, "(limit 0.012)")
