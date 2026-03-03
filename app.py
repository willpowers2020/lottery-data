from mld.api import app

# This file is intentionally small.  It exists so that the top-level
# `python app.py` entry point still works (Gunicorn can also target
# `mld.api:app`).

if __name__ == '__main__':
    app.run(debug=True, port=5001)
