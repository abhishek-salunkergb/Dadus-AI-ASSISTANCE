#!/usr/bin/env python
"""DADUS - Personal AI Operating Assistant Runner.
Usage:
  python run.py             # Start web/desktop interface
  python run.py --cli       # Start interactive CLI mode
  python run.py --voice     # Start continuous voice wake-word monitoring
  python run.py --window    # Start in dedicated desktop window (via pywebview)
"""
import sys
from app.main import main

if __name__ == "__main__":
    main()
