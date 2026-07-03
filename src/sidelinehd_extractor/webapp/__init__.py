"""Local web UI for the extraction pipeline.

Requires the optional ``web`` dependencies (``pip install -e ".[web]"``).
This package intentionally imports nothing at the top level so that the core
CLI install never pays for (or breaks on) the web stack; import
``sidelinehd_extractor.webapp.app`` to build the FastAPI application.
"""
