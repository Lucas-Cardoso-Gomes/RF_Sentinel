# utils/win_dll_fix.py
import os
import sys
from pathlib import Path

RADI_CONDA_BASES = [
    r"C:\ProgramData\radioconda\Library\bin",
    r"C:\ProgramData\radioconda\Library\lib",
]

def apply():
    if sys.platform != "win32":
        return

    if not hasattr(os, "add_dll_directory"):
        return

    for p in RADI_CONDA_BASES:
        if os.path.isdir(p):
            os.add_dll_directory(p)
