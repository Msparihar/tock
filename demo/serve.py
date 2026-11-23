"""Serve tock in a browser tab (xterm.js) so the demo can be recorded in a real browser.

Usage: uv run python demo/serve.py [port]   (TOCK_HOME picks the state folder)
"""
import os
import sys

from textual_serve.server import Server

port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
os.environ.setdefault("TOCK_HOME", os.path.join(os.path.dirname(__file__), "out", "home"))
Server("uv run tock", host="127.0.0.1", port=port, title="tock").serve()
