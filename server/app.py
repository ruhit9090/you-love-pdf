from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import pymupdf
import io
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


@app.route("/compress", methods=["POST"])
def compress_pdf():

    if "file" not in request.files:
        return jsonify({
            "status": "error",
            "message": "No PDF file received."
        }), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({
            "status": "error",
            "message": "No PDF file selected."
        }), 400

    try:

        original_data = file.read()

        if not original_data:
            return jsonify({
                "status": "error",
                "message": "The uploaded PDF is empty."
            }), 400

        original_size = len(original_data)

        pdf = pymupdf.open(
            stream=original_data,
            filetype="pdf"
        )

        output = io.BytesIO()

        pdf.save(
            output,
            garbage=4,
            clean=True,
            deflate=True,
            deflate_images=True,
            deflate_fonts=True
        )

        pdf.close()

        compressed_data = output.getvalue()
        compressed_size = len(compressed_data)

        # If compression does not make the file smaller,
        # keep the original PDF.
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

        print("Compression error:", error)

        return jsonify({
            "status": "error",
            "message": "PDF compression failed."
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
