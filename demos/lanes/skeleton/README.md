# Ridgeline

A trail board: a Python backend serves trail data as JSON, and a browser page lists it.

Run it from this folder:

```
python backend/server.py
```

Then open http://127.0.0.1:8000. `--port 8123` picks another port.

Each lane has its own tests:

```
python -m unittest discover -s backend
node --test frontend/render.test.js
```

The repo is split into two lanes; `LANES.md` says which files belong to which.
