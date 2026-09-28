from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import io
import os
import time
import requests
import jwt

app = Flask(__name__)
CORS(app)

ILOVEAPI_PUBLIC_KEY = os.environ.get("ILOVEPDF_PUBLIC_KEY")
ILOVEAPI_SECRET_KEY = os.environ.get("ILOVEPDF_SECRET_KEY")

API_BASE = "https://api.ilovepdf.com/v1"

# iLoveAPI token lifetime is 1 hour.
# This delay also helps with server clock differences.
TOKEN_EXPIRE_SECONDS = 3600
TIME_DELAY_SECONDS = 5400


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


def create_token():
    if not ILOVEAPI_PUBLIC_KEY or not ILOVEAPI_SECRET_KEY:
        raise Exception("iLoveAPI credentials are not configured.")

    now = int(time.time())

    payload = {
        "iss": "",
        "aud": "",
        "iat": now - TIME_DELAY_SECONDS,
        "nbf": now - TIME_DELAY_SECONDS,
        "exp": now + TOKEN_EXPIRE_SECONDS + TIME_DELAY_SECONDS,
        "jti": ILOVEAPI_PUBLIC_KEY
    }

    token = jwt.encode(
        payload,
        ILOVEAPI_SECRET_KEY,
        algorithm="HS256"
    )

    return token


@app.route("/compress", methods=["POST"])
def compress_pdf():

    if "file" not in request.files:
        return jsonify({
            "status": "error",
            "message": "No PDF file received."
        }), 400

    file = request.files["file"]

    if not file.filename:
        return jsonify({
            "status": "error",
            "message": "No PDF file selected."
        }), 400

    if not file.filename.lower().endswith(".pdf"):
        return jsonify({
            "status": "error",
            "message": "Please upload a PDF file."
        }), 400

    try:
        original_data = file.read()

        if not original_data:
            return jsonify({
                "status": "error",
                "message": "The uploaded PDF is empty."
            }), 400

        original_size = len(original_data)

        # ---------------------------------
        # 1. Create authentication token
        # ---------------------------------

        token = create_token()

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        }

        # ---------------------------------
        # 2. Start compression task
        # ---------------------------------

        start_response = requests.get(
            f"{API_BASE}/start/compress/in",
            headers=headers,
            timeout=60
        )

        if not start_response.ok:
            raise Exception(
                f"iLoveAPI start failed: {start_response.text}"
            )

        start_data = start_response.json()

        server = start_data["server"]
        task_id = start_data["task"]

        # ---------------------------------
        # 3. Upload PDF
        # ---------------------------------

        upload_url = f"https://{server}/v1/upload"

        upload_response = requests.post(
            upload_url,
            headers=headers,
            data={
                "task": task_id
            },
            files={
                "file": (
                    file.filename,
                    original_data,
                    "application/pdf"
                )
            },
            timeout=300
        )

        if not upload_response.ok:
            raise Exception(
                f"iLoveAPI upload failed: {upload_response.text}"
            )

        upload_data = upload_response.json()

        server_filename = upload_data["server_filename"]

        # ---------------------------------
        # 4. Process compression
        # ---------------------------------

        process_url = f"https://{server}/v1/process"

        process_payload = {
            "task": task_id,
            "tool": "compress",
            "files": [
                {
                    "server_filename": server_filename,
                    "filename": file.filename
                }
            ],
            "compression_level": "recommended"
        }

        process_response = requests.post(
            process_url,
            headers={
                **headers,
                "Content-Type": "application/json"
            },
            json=process_payload,
            timeout=600
        )

        if not process_response.ok:
            raise Exception(
                f"iLoveAPI process failed: {process_response.text}"
            )

        # ---------------------------------
        # 5. Download compressed PDF
        # ---------------------------------

        download_url = f"https://{server}/v1/download/{task_id}"

        download_response = requests.get(
            download_url,
            headers=headers,
            timeout=600
        )

        if not download_response.ok:
            raise Exception(
                f"iLoveAPI download failed: {download_response.text}"
            )

        compressed_data = download_response.content
        compressed_size = len(compressed_data)

        # ---------------------------------
        # 6. Never return a larger PDF
        # ---------------------------------

        if compressed_size >= original_size:
            return send_file(
                io.BytesIO(original_data),
                mimetype="application/pdf",
                as_attachment=True,
                download_name="compressed-" + file.filename
            )

        return send_file(
            io.BytesIO(compressed_data),
            mimetype="application/pdf",
            as_attachment=True,
            download_name="compressed-" + file.filename
        )

    except Exception as error:
        print("iLoveAPI compression error:", error)

        return jsonify({
            "status": "error",
            "message": "PDF compression failed. Please try again."
        }), 500


if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
