# ═══════════════════════════════════════════════════════
# CORS PATCH for app.py — Add this near the top of app.py
# (after "app = Flask(__name__)")
# ═══════════════════════════════════════════════════════
#
# Option A: Install flask-cors (recommended)
#   pip install flask-cors
#   Then add after app = Flask(__name__):

from flask_cors import CORS
CORS(app)

# Option B: Manual CORS (no extra package)
#   Add this after app = Flask(__name__):

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
    response.headers.add('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
    return response

# ═══════════════════════════════════════════════════════
# USE EITHER Option A or Option B, not both
# ═══════════════════════════════════════════════════════
