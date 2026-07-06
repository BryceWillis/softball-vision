"""PyInstaller entry script for the macOS .app bundle (item 54d).

Kept to one import + call so all real logic lives in the testable
``sidelinehd_extractor.desktop`` module.
"""

from sidelinehd_extractor.desktop import main

raise SystemExit(main())
