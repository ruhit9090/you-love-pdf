from flask import Flask, jsonify
from flask_cors import CORS
import os

app = Flask(__name__)
CORS(app)

@app.route("/")
def home():
    return jsonify({
        "status": "success",
        "message": "You Love PDF backend is running!"
    })

@app.route("/health")
def health():
    return jsonify({
        "status": "ok"
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
