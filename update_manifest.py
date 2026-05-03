"""Update docs/manifest.json with a new month entry."""
import json
import os
import sys

month = sys.argv[1]
path = "docs/manifest.json"

manifest = json.load(open(path)) if os.path.exists(path) else {"months": []}
if month not in manifest["months"]:
    manifest["months"].append(month)
    manifest["months"].sort()
manifest["latest"] = manifest["months"][-1] if manifest["months"] else None

with open(path, "w") as f:
    json.dump(manifest, f, indent=2)
    f.write("\n")

print(f"Manifest updated: {manifest}")
