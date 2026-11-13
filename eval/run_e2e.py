#!/usr/bin/env python3
"""Repository entry point for the AgentCube E2E integration."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.e2e.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
