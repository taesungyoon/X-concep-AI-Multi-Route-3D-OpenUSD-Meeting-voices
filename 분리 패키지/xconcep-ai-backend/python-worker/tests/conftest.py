import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("OPENAI_IMAGE_MODE", "mock")
os.environ.setdefault("SHAPE_MODE", "mock")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
