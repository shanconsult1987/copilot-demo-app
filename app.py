from flask import Flask, jsonify, request

app = Flask(__name__)

@app.route("/")
def home():
    return "Copilot Demo App 🚀"

@app.route("/api/data", methods=["GET"])
def get_data():
    return jsonify({"message": "Hello from Copilot demo!"})

@app.route("/api/add", methods=["POST"])
def add_numbers():
    data = request.json
    result = data.get("a", 0) + data.get("b", 0)
    return jsonify({"result": result})

if __name__ == "__main__":
    app.run(debug=True)
