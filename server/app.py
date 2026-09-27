from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import os
import fitz
import tempfile

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
            "message": "No PDF file provided"
        }), 400

    uploaded_file = request.files["file"]

    if uploaded_file.filename == "":
        return jsonify({
            "status": "error",
            "message": "No file selected"
        }), 400

    if not uploaded_file.filename.lower().endswith(".pdf"):
        return jsonify({
            "status": "error",
            "message": "Only PDF files are allowed"
        }), 400

    input_path = None
    output_path = None

    try:
        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".pdf"
        ) as temp_input:

            uploaded_file.save(temp_input.name)
            input_path = temp_input.name

        input_size = os.path.getsize(input_path)

        doc = fitz.open(input_path)

        output_file = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".pdf"
        )
        output_path = output_file.name
        output_file.close()

        doc.save(
            output_path,
            garbage=4,
            deflate=True,
            clean=True
        )

        doc.close()

        output_size = os.path.getsize(output_path)

        if output_size >= input_size:
            os.replace(input_path, output_path)
            input_path = None

        return send_file(
            output_path,
            as_attachment=True,
            download_name="compressed.pdf",
            mimetype="application/pdf"
        )

    except Exception as e:

        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

    finally:

        if input_path and os.path.exists(input_path):
            os.remove(input_path)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
