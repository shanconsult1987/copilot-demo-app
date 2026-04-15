from dotenv import load_dotenv

# Load .env file when running locally (no-op in production where env vars are
# injected directly).
load_dotenv()

from flask import Flask, jsonify, request  # noqa: E402
from auth import require_auth  # noqa: E402

app = Flask(__name__)


@app.route("/")
def home():
    return "Copilot Demo App 🚀"


@app.route("/api/data", methods=["GET"])
@require_auth
def get_data():
    """Protected endpoint – requires a valid Entra ID Bearer token."""
    return jsonify({"message": "Hello from Copilot demo!"})


@app.route("/api/add", methods=["POST"])
@require_auth
def add_numbers():
    """Protected endpoint – requires a valid Entra ID Bearer token."""
    data = request.json or {}
    a = data.get("a", 0)
    b = data.get("b", 0)
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        return jsonify({"error": "Both 'a' and 'b' must be numbers"}), 400
    return jsonify({"result": a + b})


if __name__ == "__main__":
    app.run(debug=True)
