
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import io
import os
import time
import json
import requests
import jwt


app = Flask(__name__)
CORS(app)


# =========================================================
# ILOVEAPI SETTINGS
# =========================================================

ILOVEPDF_PUBLIC_KEY = os.environ.get("ILOVEPDF_PUBLIC_KEY")
ILOVEPDF_SECRET_KEY = os.environ.get("ILOVEPDF_SECRET_KEY")

API_BASE = "https://api.ilovepdf.com/v1"

TOKEN_EXPIRE_SECONDS = 3600
TIME_DELAY_SECONDS = 5400


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():
    return jsonify({
        "status": "success",
        "message": "You Love PDF backend is running!"
    })


# =========================================================
# HEALTH
# =========================================================

@app.route("/health")
def health():
    return jsonify({
        "status": "ok"
    })


# =========================================================
# CREATE ILOVEAPI TOKEN
# =========================================================

def create_token():

    if not ILOVEPDF_PUBLIC_KEY or not ILOVEPDF_SECRET_KEY:
        raise Exception(
            "ILOVEPDF_PUBLIC_KEY or ILOVEPDF_SECRET_KEY is not configured."
        )

    now = int(time.time())

    payload = {
        "iss": "",
        "aud": "",
        "iat": now - TIME_DELAY_SECONDS,
        "nbf": now - TIME_DELAY_SECONDS,
        "exp": now + TOKEN_EXPIRE_SECONDS + TIME_DELAY_SECONDS,
        "jti": ILOVEPDF_PUBLIC_KEY
    }

    token = jwt.encode(
        payload,
        ILOVEPDF_SECRET_KEY,
        algorithm="HS256"
    )

    return token


# =========================================================
# COMMON API FUNCTIONS
# =========================================================

def api_headers():
    return {
        "Authorization": f"Bearer {create_token()}",
        "Accept": "application/json"
    }


def start_task(tool):
    headers = api_headers()

    response = requests.get(
        f"{API_BASE}/start/{tool}/in",
        headers=headers,
        timeout=60
    )

    if not response.ok:
        raise Exception(
            f"iLoveAPI start failed: {response.text}"
        )

    data = response.json()

    if "server" not in data or "task" not in data:
        raise Exception(
            f"Invalid iLoveAPI start response: {data}"
        )

    return data["server"], data["task"], headers


def upload_file(
    server,
    task_id,
    headers,
    filename,
    file_data,
    mimetype
):
    upload_url = f"https://{server}/v1/upload"

    response = requests.post(
        upload_url,
        headers=headers,
        data={
            "task": task_id
        },
        files={
            "file": (
                filename,
                file_data,
                mimetype
            )
        },
        timeout=300
    )

    if not response.ok:
        raise Exception(
            f"iLoveAPI upload failed: {response.text}"
        )

    data = response.json()

    if "server_filename" not in data:
        raise Exception(
            f"Invalid iLoveAPI upload response: {data}"
        )

    return data["server_filename"]


def process_task(
    server,
    task_id,
    headers,
    tool,
    files,
    extra=None
):
    process_url = f"https://{server}/v1/process"

    payload = {
        "task": task_id,
        "tool": tool,
        "files": files
    }

    if extra:
        payload.update(extra)

    response = requests.post(
        process_url,
        headers={
            **headers,
            "Content-Type": "application/json"
        },
        json=payload,
        timeout=600
    )

    if not response.ok:
        raise Exception(
            f"iLoveAPI process failed: {response.text}"
        )

    return response.json()


def download_result(server, task_id, headers):
    download_url = f"https://{server}/v1/download/{task_id}"

    response = requests.get(
        download_url,
        headers=headers,
        timeout=600
    )

    if not response.ok:
        raise Exception(
            f"iLoveAPI download failed: {response.text}"
        )

    return (
        response.content,
        response.headers.get(
            "Content-Type",
            "application/octet-stream"
        )
    )


def convert_pages_to_ranges(pages):
    numbers = []

    for page in pages:
        try:
            number = int(page)
        except Exception:
            continue

        if number > 0 and number not in numbers:
            numbers.append(number)

    numbers.sort()

    if not numbers:
        return None

    ranges = []

    start = numbers[0]
    previous = numbers[0]

    for number in numbers[1:]:

        if number == previous + 1:
            previous = number
            continue

        if start == previous:
            ranges.append(str(start))
        else:
            ranges.append(
                f"{start}-{previous}"
            )

        start = number
        previous = number

    if start == previous:
        ranges.append(str(start))
    else:
        ranges.append(
            f"{start}-{previous}"
        )

    return ",".join(ranges)


# =========================================================
# 1. COMPRESS PDF
# =========================================================

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

        server, task_id, headers = start_task("compress")

        server_filename = upload_file(
            server,
            task_id,
            headers,
            file.filename,
            original_data,
            "application/pdf"
        )

        process_task(
            server,
            task_id,
            headers,
            "compress",
            [{
                "server_filename": server_filename,
                "filename": file.filename
            }],
            {
                "compression_level": "recommended"
            }
        )

        compressed_data, _ = download_result(
            server,
            task_id,
            headers
        )

        if len(compressed_data) >= len(original_data):
            return send_file(
                io.BytesIO(original_data),
                mimetype="application/pdf",
                as_attachment=True,
                download_name=f"compressed-{file.filename}"
            )

        return send_file(
            io.BytesIO(compressed_data),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"compressed-{file.filename}"
        )

    except Exception as error:

        print("iLoveAPI compression error:", error)

        return jsonify({
            "status": "error",
            "message": "PDF compression failed. Please try again."
        }), 500


# =========================================================
# 2. MERGE PDF
# =========================================================

@app.route("/merge", methods=["POST"])
def merge_pdf():

    files = request.files.getlist("files")

    if len(files) < 2:
        return jsonify({
            "status": "error",
            "message": "Please upload at least 2 PDF files."
        }), 400

    try:

        server, task_id, headers = start_task("merge")

        uploaded_files = []

        for file in files:

            if not file.filename:
                continue

            if not file.filename.lower().endswith(".pdf"):
                raise Exception(
                    f"Invalid PDF file: {file.filename}"
                )

            file_data = file.read()

            if not file_data:
                raise Exception(
                    f"Empty PDF file: {file.filename}"
                )

            server_filename = upload_file(
                server,
                task_id,
                headers,
                file.filename,
                file_data,
                "application/pdf"
            )

            uploaded_files.append({
                "server_filename": server_filename,
                "filename": file.filename
            })

        if len(uploaded_files) < 2:
            return jsonify({
                "status": "error",
                "message": "Please upload at least 2 valid PDF files."
            }), 400

        process_task(
            server,
            task_id,
            headers,
            "merge",
            uploaded_files
        )

        merged_data, _ = download_result(
            server,
            task_id,
            headers
        )

        return send_file(
            io.BytesIO(merged_data),
            mimetype="application/pdf",
            as_attachment=True,
            download_name="merged.pdf"
        )

    except Exception as error:

        print("iLoveAPI merge error:", error)

        return jsonify({
            "status": "error",
            "message": "PDF merging failed. Please try again."
        }), 500


# =========================================================
# 3. SPLIT PDF
# =========================================================

@app.route("/split", methods=["POST"])
def split_pdf():

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

    pages_text = request.form.get("pages")

    if not pages_text:
        return jsonify({
            "status": "error",
            "message": "No pages selected."
        }), 400

    try:
        pages = json.loads(pages_text)
    except Exception:
        return jsonify({
            "status": "error",
            "message": "Invalid page selection."
        }), 400

    if not isinstance(pages, list):
        return jsonify({
            "status": "error",
            "message": "Invalid page selection."
        }), 400

    ranges = convert_pages_to_ranges(pages)

    if not ranges:
        return jsonify({
            "status": "error",
            "message": "No valid pages selected."
        }), 400

    try:

        file_data = file.read()

        if not file_data:
            return jsonify({
                "status": "error",
                "message": "The uploaded PDF is empty."
            }), 400

        server, task_id, headers = start_task("split")

        server_filename = upload_file(
            server,
            task_id,
            headers,
            file.filename,
            file_data,
            "application/pdf"
        )

        process_task(
            server,
            task_id,
            headers,
            "split",
            [{
                "server_filename": server_filename,
                "filename": file.filename
            }],
            {
                "ranges": ranges,
                "merge_after": True
            }
        )

        split_data, content_type = download_result(
            server,
            task_id,
            headers
        )

        return send_file(
            io.BytesIO(split_data),
            mimetype=content_type,
            as_attachment=True,
            download_name="split.pdf"
            if "pdf" in content_type.lower()
            else "split.zip"
        )

    except Exception as error:

        print("iLoveAPI split error:", error)

        return jsonify({
            "status": "error",
            "message": "PDF splitting failed. Please try again."
        }), 500


# =========================================================
# 4. JPG / IMAGE TO PDF
# =========================================================

@app.route("/jpg-to-pdf", methods=["POST"])
def jpg_to_pdf():

    files = request.files.getlist("files")

    if not files:
        return jsonify({
            "status": "error",
            "message": "Please upload at least one image."
        }), 400

    try:

        server, task_id, headers = start_task("imagepdf")

        uploaded_files = []

        for file in files:

            if not file.filename:
                continue

            filename = file.filename.lower()

            allowed = (
                filename.endswith(".jpg")
                or filename.endswith(".jpeg")
                or filename.endswith(".png")
                or filename.endswith(".tif")
                or filename.endswith(".tiff")
            )

            if not allowed:
                raise Exception(
                    f"Unsupported image type: {file.filename}"
                )

            image_data = file.read()

            if not image_data:
                raise Exception(
                    f"Empty image file: {file.filename}"
                )

            if filename.endswith(
                (".jpg", ".jpeg")
            ):
                mimetype = "image/jpeg"

            elif filename.endswith(".png"):
                mimetype = "image/png"

            else:
                mimetype = "image/tiff"

            server_filename = upload_file(
                server,
                task_id,
                headers,
                file.filename,
                image_data,
                mimetype
            )

            uploaded_files.append({
                "server_filename": server_filename,
                "filename": file.filename
            })

        if not uploaded_files:
            return jsonify({
                "status": "error",
                "message": "No valid images found."
            }), 400

        process_task(
            server,
            task_id,
            headers,
            "imagepdf",
            uploaded_files
        )

        pdf_data, _ = download_result(
            server,
            task_id,
            headers
        )

        return send_file(
            io.BytesIO(pdf_data),
            mimetype="application/pdf",
            as_attachment=True,
            download_name="jpg-to-pdf.pdf"
        )

    except Exception as error:

        print("iLoveAPI JPG to PDF error:", error)

        return jsonify({
            "status": "error",
            "message": "JPG to PDF conversion failed. Please try again."
        }), 500


# =========================================================
# 5. PDF TO JPG
# =========================================================

@app.route("/pdf-to-jpg", methods=["POST"])
def pdf_to_jpg():

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

    pages_text = request.form.get("pages")

    if not pages_text:
        return jsonify({
            "status": "error",
            "message": "No pages selected."
        }), 400

    try:
        pages = json.loads(pages_text)
    except Exception:
        return jsonify({
            "status": "error",
            "message": "Invalid page selection."
        }), 400

    if not isinstance(pages, list):
        return jsonify({
            "status": "error",
            "message": "Invalid page selection."
        }), 400

    ranges = convert_pages_to_ranges(pages)

    if not ranges:
        return jsonify({
            "status": "error",
            "message": "No valid pages selected."
        }), 400

    try:

        file_data = file.read()

        if not file_data:
            return jsonify({
                "status": "error",
                "message": "The uploaded PDF is empty."
            }), 400

        server, task_id, headers = start_task("pdfjpg")

        server_filename = upload_file(
            server,
            task_id,
            headers,
            file.filename,
            file_data,
            "application/pdf"
        )

        process_task(
            server,
            task_id,
            headers,
            "pdfjpg",
            [{
                "server_filename": server_filename,
                "filename": file.filename
            }],
            {
                "pages": ranges
            }
        )

        jpg_data, content_type = download_result(
            server,
            task_id,
            headers
        )

        return send_file(
            io.BytesIO(jpg_data),
            mimetype=content_type,
            as_attachment=True,
            download_name="pdf-to-jpg.zip"
        )

    except Exception as error:

        print("iLoveAPI PDF to JPG error:", error)

        return jsonify({
            "status": "error",
            "message": "PDF to JPG conversion failed. Please try again."
        }), 500


# =========================================================
# RUN SERVER
# =========================================================

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

