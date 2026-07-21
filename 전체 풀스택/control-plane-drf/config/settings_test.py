import os
import tempfile
from pathlib import Path


os.environ['DB_ENGINE'] = 'sqlite'
os.environ.setdefault('SYNC_PIPELINE', 'true')
os.environ['STORAGE_PATH'] = str(Path(tempfile.gettempdir()) / 'xconcep-control-plane-tests')

from .settings import *  # noqa: F401,F403,E402
