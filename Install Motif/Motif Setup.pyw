"""Open Motif Setup on Windows, with no console window."""
import runpy
import sys
from pathlib import Path

here = Path(__file__).resolve().parent.parent
sys.argv = [str(here / 'setup' / 'motif_setup.py')]
runpy.run_path(str(here / 'setup' / 'motif_setup.py'),
               run_name='__main__')
