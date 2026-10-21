from flask import Flask, request, jsonify
import importlib.util
import os
from concurrent.futures import ThreadPoolExecutor
import requests

# ── استيراد الأداة ────────────────────────────
SCRIPT_NAME = "vbv"

spec = importlib.util.spec_from_file_location(
    SCRIPT_NAME,
    os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{SCRIPT_NAME}.py")
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

DEV_NAME = "https://t.me/afuonaz"

# ── 5 عمال متوازيين + طابور ──────────────────────
executor = ThreadPoolExecutor(max_workers=5)

app = Flask(__name__)

# ── Auth cache (يتجدد لو فشل) ────────────────────
_auth_cache = {"auth": None, "merch": None, "session": None}


def get_auth(force_refresh=False):
    """يرجع (session, auth, merch) — مع cache"""
    if not force_refresh and _auth_cache["auth"]:
        return _auth_cache["session"], _auth_cache["auth"], _auth_cache["merch"]

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/148.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-GB,en;q=0.9",
    })
    auth, merch = module.extract_auth(session)
    if auth:
        _auth_cache["auth"] = auth
        _auth_cache["merch"] = merch
        _auth_cache["session"] = session
    return session, auth, merch


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "developer": DEV_NAME,
        "status": "running"
    }), 200


@app.route("/vbv", methods=["POST", "GET"])
def vbv():
    try:
        if request.method == "GET":
            card = (request.args.get("card") or "").strip()
            show_bin = (request.args.get("bin") or "").lower() in ("1", "true", "yes")
        else:
            data = request.get_json(silent=True) or {}
            card = (data.get("card") or "").strip()
            show_bin = bool(data.get("bin", False))

        if not card:
            return jsonify({"developer": DEV_NAME, "error": "Missing 'card'"}), 400

        if len(card.replace("/", "|").split("|")) < 4:
            return jsonify({"developer": DEV_NAME, "error": "Format: CC|MM|YY|CVV"}), 400

        def _run():
            sess, auth, merch = get_auth()
            if not auth:
                # retry once
                sess, auth, merch = get_auth(force_refresh=True)
            if not auth:
                return {"status": "ERROR", "message": "AUTH_FAILED", "brand": "UNKNOWN",
                        "last4": "0000", "bin_info": None, "time": 0}
            return module.check_card(sess, auth, merch, card, show_bin=show_bin)

        future = executor.submit(_run)
        result = future.result(timeout=120)

        return jsonify({
            "developer": DEV_NAME,
            "status": result.get("status", "UNKNOWN"),
            "message": result.get("message", ""),
            "enrolled": result.get("enrolled", "UNKNOWN"),
            "brand": result.get("brand", "UNKNOWN"),
            "last4": result.get("last4", "0000"),
            "bin": result.get("bin_info"),
            "time": round(result.get("time", 0), 2)
        }), 200

    except Exception as e:
        return jsonify({"developer": DEV_NAME, "error": str(e)}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "developer": DEV_NAME,
        "status": "ok"
    }), 200


if __name__ == "__main__":
    print(f"[*] VBV API started — Dev: {DEV_NAME}")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)