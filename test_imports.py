import pkgutil
import importlib
import traceback
import sys
import project_alpha

print("Starting Module Validation...")

errors = 0
for m in pkgutil.walk_packages(project_alpha.__path__, project_alpha.__name__ + "."):
    try:
        importlib.import_module(m.name)
    except Exception as e:
        print(f"BROKEN IMPORT in {m.name}: {e}")
        errors += 1

print(f"Validation Complete. Errors found: {errors}")
if errors > 0:
    sys.exit(1)
