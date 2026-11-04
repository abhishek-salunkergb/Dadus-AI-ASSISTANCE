#!/usr/bin/env python
"""DADUS - Personal AI Operating Assistant Runner.
Usage:
  python run.py             # Start web/desktop interface
  python run.py --cli       # Start interactive CLI mode
  python run.py --voice     # Start continuous voice wake-word monitoring
  python run.py --tray      # Start silently in Windows System Tray (Siri-style daemon)
  python run.py --window    # Start in dedicated desktop window (via pywebview)
"""
import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.main import main

if __name__ == "__main__":
    main()
