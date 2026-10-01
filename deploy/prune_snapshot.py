"""Keep only the champion model in a deployment snapshot (the Space clone).

    python deploy/prune_snapshot.py space
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

root = Path(sys.argv[1] if len(sys.argv) > 1 else "space")
models = root / "artifacts" / "models"
reg = models / "registry.json"
idx = json.loads(reg.read_text(encoding="utf-8-sig"))
champ = idx["champion"]
for d in models.iterdir():
    if d.is_dir() and d.name != champ:
        shutil.rmtree(d)
idx["versions"] = [v for v in idx["versions"] if v["version"] == champ]
reg.write_text(json.dumps(idx, indent=2, default=str), encoding="utf-8")  # no BOM
print("champion kept:", champ)
