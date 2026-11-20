"""Launcher: the command lives in tools/perseus.py (python perseus.py edit, build, add ...)."""
import runpy
import sys
from pathlib import Path

tools = Path(__file__).resolve().parent / "tools"
sys.path.insert(0, str(tools))
runpy.run_path(str(tools / "perseus.py"), run_name="__main__")
