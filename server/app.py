from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import io
import os
import time
import json
import zipfile
import requests
import jwt
import fitz


app = Flask(__name__)
CORS(app)


# =========================================================
# ILOVEAPI SETTINGS
# =========================================================

ILOVEAPI_PUBLIC_KEY = os.environ.get("ILOVEPDF_PUBLIC_KEY")
ILOVEAPI_SECRET_KEY = os.environ.get("ILOVEPDF_SECRET_KEY")

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

        original_size = len(original_data)

        # Create token
        token = create_token()

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        }

        # Start task
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

        # Upload PDF
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

        # Process
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

        # Download
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

        # If compression makes file larger, return original
        if compressed_size >= original_size:

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

        # Create token
        token = create_token()

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        }

        # Start merge task
        start_response = requests.get(
            f"{API_BASE}/start/merge/in",
            headers=headers,
            timeout=60
        )

        if not start_response.ok:
            raise Exception(
                f"iLoveAPI merge start failed: {start_response.text}"
            )

        start_data = start_response.json()

        server = start_data["server"]
        task_id = start_data["task"]

        # Upload files
        uploaded_files = []

        upload_url = f"https://{server}/v1/upload"

        for file in files:

            if not file.filename:
                raise Exception("A selected file has no filename.")

            if not file.filename.lower().endswith(".pdf"):
                raise Exception(
                    f"Invalid file type: {file.filename}"
                )

            file_data = file.read()

            if not file_data:
                raise Exception(
                    f"Empty PDF file: {file.filename}"
                )

            upload_response = requests.post(
                upload_url,
                headers=headers,
                data={
                    "task": task_id
                },
                files={
                    "file": (
                        file.filename,
                        file_data,
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

            uploaded_files.append({
                "server_filename": upload_data["server_filename"],
                "filename": file.filename
            })

        # Process merge
        process_url = f"https://{server}/v1/process"

        process_payload = {
            "task": task_id,
            "tool": "merge",
            "files": uploaded_files
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
                f"iLoveAPI merge process failed: "
                f"{process_response.text}"
            )

        # Download merged PDF
        download_url = f"https://{server}/v1/download/{task_id}"

        download_response = requests.get(
            download_url,
            headers=headers,
            timeout=600
        )

        if not download_response.ok:
            raise Exception(
                f"iLoveAPI merge download failed: "
                f"{download_response.text}"
            )

        merged_data = download_response.content

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

    try:

        pdf_data = file.read()

        if not pdf_data:
            return jsonify({
                "status": "error",
                "message": "The uploaded PDF is empty."
            }), 400

        # Get selected pages
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

        # Open PDF
        source_pdf = fitz.open(
            stream=pdf_data,
            filetype="pdf"
        )

        page_count = len(source_pdf)

        if page_count == 0:
            source_pdf.close()

            return jsonify({
                "status": "error",
                "message": "The PDF contains no pages."
            }), 400

        # Validate pages
        valid_pages = []

        for page in pages:

            try:
                page_number = int(page)
            except Exception:
                continue

            if 1 <= page_number <= page_count:

                if page_number not in valid_pages:
                    valid_pages.append(page_number)

        if not valid_pages:

            source_pdf.close()

            return jsonify({
                "status": "error",
                "message": "No valid pages selected."
            }), 400

        # Create new PDF
        output_pdf = fitz.open()

        for page_number in valid_pages:

            output_pdf.insert_pdf(
                source_pdf,
                from_page=page_number - 1,
                to_page=page_number - 1
            )

        output_data = output_pdf.tobytes()

        output_pdf.close()
        source_pdf.close()

        return send_file(
            io.BytesIO(output_data),
            mimetype="application/pdf",
            as_attachment=True,
            download_name="split.pdf"
        )

    except Exception as error:

        print("Split PDF error:", error)

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
            "message": "Please upload at least one JPG image."
        }), 400

    try:

        output_pdf = fitz.open()

        # A4 size in points
        A4_WIDTH = 595.28
        A4_HEIGHT = 841.89

        MARGIN = 28.35

        usable_width = A4_WIDTH - (MARGIN * 2)
        usable_height = A4_HEIGHT - (MARGIN * 2)

        valid_image_count = 0

        # Process images in order
        for file in files:

            if not file.filename:
                continue

            filename = file.filename.lower()

            if not (
                filename.endswith(".jpg")
                or filename.endswith(".jpeg")
            ):
                output_pdf.close()

                return jsonify({
                    "status": "error",
                    "message": "Only JPG/JPEG images are supported."
                }), 400

            image_data = file.read()

            if not image_data:
                output_pdf.close()

                return jsonify({
                    "status": "error",
                    "message": "One of the selected images is empty."
                }), 400

            # Read image dimensions
            try:
                image_pixmap = fitz.Pixmap(
                    stream=image_data
                )

                image_width = image_pixmap.width
                image_height = image_pixmap.height

            except Exception:

                output_pdf.close()

                return jsonify({
                    "status": "error",
                    "message": f"Invalid JPG image: {file.filename}"
                }), 400

            if image_width <= 0 or image_height <= 0:

                output_pdf.close()

                return jsonify({
                    "status": "error",
                    "message": "Invalid JPG image."
                }), 400

            # Calculate fit
            scale_x = usable_width / image_width
            scale_y = usable_height / image_height

            scale = min(scale_x, scale_y)

            display_width = image_width * scale
            display_height = image_height * scale

            x = (A4_WIDTH - display_width) / 2
            y = (A4_HEIGHT - display_height) / 2

            image_rect_on_pdf = fitz.Rect(
                x,
                y,
                x + display_width,
                y + display_height
            )

            # Create PDF page
            page = output_pdf.new_page(
                width=A4_WIDTH,
                height=A4_HEIGHT
            )

            # Insert image
            page.insert_image(
                image_rect_on_pdf,
                stream=image_data,
                keep_proportion=True
            )

            valid_image_count += 1

        if valid_image_count == 0:

            output_pdf.close()

            return jsonify({
                "status": "error",
                "message": "No valid JPG images found."
            }), 400

        # Create PDF data
        pdf_data = output_pdf.tobytes()

        output_pdf.close()

        return send_file(
            io.BytesIO(pdf_data),
            mimetype="application/pdf",
            as_attachment=True,
            download_name="jpg-to-pdf.pdf"
        )

    except Exception as error:

        print("JPG to PDF error:", error)

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

    try:

        pdf_data = file.read()

        if not pdf_data:
            return jsonify({
                "status": "error",
                "message": "The uploaded PDF is empty."
            }), 400

        # Get selected pages
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

        # Open PDF
        pdf_document = fitz.open(
            stream=pdf_data,
            filetype="pdf"
        )

        total_pages = len(pdf_document)

        if total_pages == 0:
            pdf_document.close()

            return jsonify({
                "status": "error",
                "message": "The PDF contains no pages."
            }), 400

        # Validate selected pages
        valid_pages = []

        for page in pages:

            try:
                page_number = int(page)
            except Exception:
                continue

            if 1 <= page_number <= total_pages:

                if page_number not in valid_pages:
                    valid_pages.append(page_number)

        if not valid_pages:

            pdf_document.close()

            return jsonify({
                "status": "error",
                "message": "No valid pages selected."
            }), 400

        # Create ZIP
        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(
            zip_buffer,
            mode="w",
            compression=zipfile.ZIP_DEFLATED
        ) as zip_file:

            # Convert each page
            for page_number in valid_pages:

                page = pdf_document[
                    page_number - 1
                ]

                # 2x resolution
                matrix = fitz.Matrix(
                    2,
                    2
                )

                pixmap = page.get_pixmap(
                    matrix=matrix,
                    alpha=False
                )

                jpg_data = pixmap.tobytes(
                    "jpeg"
                )

                zip_file.writestr(
                    f"page-{page_number}.jpg",
                    jpg_data
                )

        pdf_document.close()

        # Prepare ZIP
        zip_buffer.seek(0)

        return send_file(
            zip_buffer,
            mimetype="application/zip",
            as_attachment=True,
            download_name="pdf-to-jpg.zip"
        )

    except Exception as error:

        print("PDF to JPG error:", error)

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
