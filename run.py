import os
import sys
import uvicorn

# Ensure UTF-8 output encoding for Windows terminals
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "127.0.0.1")
    print(f"Starting Acer Amazon Price Intelligence Server on http://{host}:{port}")
    uvicorn.run("app.main:app", host=host, port=port, reload=True)
