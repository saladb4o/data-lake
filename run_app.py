"""
=============================================================================
VNSTOCK MONITOR - APPLICATION LAUNCHER
=============================================================================
Run this script to start the Vietnam Stock Monitor app locally:
    python run_app.py
"""

import os
import sys
import logging

logger = logging.getLogger(__name__)

# Load .env file
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    try:
        with open(_env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if k not in os.environ:
                        os.environ[k] = v
    except Exception:
        # A malformed .env means every setting silently falls back to its
        # default, which looks identical to having configured nothing.
        print("[ENV] Could not read .env; continuing with defaults")

import webbrowser
import threading
import time
import uvicorn
import services.tls_config

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        logger.debug("Could not switch the console to UTF-8", exc_info=True)

def open_browser(url: str):
    time.sleep(1.2)
    try:
        webbrowser.open(url)
    except Exception:
        print(f"[APP] Could not open a browser automatically; visit {url}")

import socket

def find_available_port(host: str = "127.0.0.1") -> int:
    candidate_ports = [8000, 8080, 8008, 8888, 5000, 5001, 8050] + list(range(8001, 8030))
    for p in candidate_ports:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, p))
                return p
            except OSError:
                continue
    return 8000

if __name__ == "__main__":
    host = "127.0.0.1"
    port = find_available_port(host)
    url = f"http://{host}:{port}"
    
    print("=" * 60)
    print(" 🚀 KHỞI ĐỘNG VIETNAM STOCK MONITOR (VNSTOCK)")
    print(f" 🌐 Địa chỉ truy cập: {url}")
    print("=" * 60)
    
    # Auto open browser in background thread
    threading.Thread(target=open_browser, args=(url,), daemon=True).start()
    
    # Run uvicorn server with auto-reload enabled
    uvicorn.run("server:app", host=host, port=port, reload=True)
