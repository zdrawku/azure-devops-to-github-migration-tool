import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from clients.ado_client import get_all_areas, get_all_iterations
import json

# Fetch the full trees
areas      = get_all_areas()
iterations = get_all_iterations()

# Pretty-print
print(json.dumps(areas, indent=2))
print(json.dumps(iterations, indent=2))

# Walk top-level children
for node in areas.get("children", []):
    print(node["name"])

# Limit depth
areas_shallow = get_all_areas(depth=2)