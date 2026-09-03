import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file
from werkzeug.utils import secure_filename

from services.local_pdf import process_local
from services.ilovepdf_api import process_ilovepdf, ilovepdf_available

BASE_DIR = Path(__file__).resolve().parent
TMP_DIR = BASE_DIR / "tmp"
TMP_DIR.mkdir(exist_ok=True)

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "50"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

ALLOWED = {
    "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx",
    "jpg", "jpeg", "png", "webp"
}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES


def cleanup_old_files(max_age_seconds=3600):
    import time
    now = time.time()
    for p in TMP_DIR.iterdir():
        try:
            if now - p.stat().st_mtime > max_age_seconds:
                if p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    p.unlink(missing_ok=True)
        except OSError:
            pass


def extension(name):
    return Path(name).suffix.lower().lstrip(".")


def save_upload(file_storage):
    if not file_storage or not file_storage.filename:
        raise ValueError("No file selected.")
    ext = extension(file_storage.filename)
    if ext not in ALLOWED:
        raise ValueError(f"Unsupported file type: .{ext or 'unknown'}")
    safe = secure_filename(file_storage.filename) or f"upload.{ext}"
    path = TMP_DIR / f"{uuid.uuid4().hex}_{safe}"
    file_storage.save(path)
    if path.stat().st_size > MAX_UPLOAD_BYTES:
        path.unlink(missing_ok=True)
        raise ValueError(f"File is larger than the {MAX_UPLOAD_MB} MB limit.")
    return path


def save_files(field="files"):
    files = request.files.getlist(field)
    if not files:
        # Also support a single `file` field.
        one = request.files.get("file")
        files = [one] if one else []
    saved = []
    try:
        for f in files:
            saved.append(save_upload(f))
        return saved
    except Exception:
        for p in saved:
            p.unlink(missing_ok=True)
        raise


def make_download(path, download_name=None):
    path = Path(path)

    return jsonify({
        "success": True,
        "filename": download_name or path.name,
        "download_url": f"/download/{path.name}"
    })


@app.route("/download/<filename>")
def download_file(filename):
    file_path = TMP_DIR / filename

    if not file_path.exists():
        return jsonify({"error": "File not found or expired."}), 404

    return send_file(
        file_path,
        as_attachment=True,
        download_name=file_path.name
    )
    


def form_value(name, default=None):
    value = request.form.get(name, default)
    return value


@app.get("/")
def index():
    cleanup_old_files()
    return render_template("index.html", max_upload_mb=MAX_UPLOAD_MB)


@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "service": "Funk File",
        "max_upload_mb": MAX_UPLOAD_MB,
        "ilovepdf_configured": ilovepdf_available(),
    })


@app.errorhandler(413)
def too_large(_):
    return jsonify({"error": f"File exceeds the {MAX_UPLOAD_MB} MB upload limit."}), 413


@app.post("/api/process")
def process():
    cleanup_old_files()
    action = (request.form.get("action") or "").strip().lower()

    valid_actions = {
        "merge", "split", "compress", "pdf-to-word", "word-to-pdf",
        "pdf-to-jpg", "pdf-to-png", "jpg-to-pdf", "png-to-pdf",
        "rotate", "delete-pages", "extract-pages", "watermark",
        "protect", "unlock"
    }
    if action not in valid_actions:
        return jsonify({"error": "Unknown PDF tool."}), 400

    uploaded = []
    output = None
    try:
        uploaded = save_files("files")
        if not uploaded:
            raise ValueError("Please select at least one file.")

        params = {
            k: v for k, v in request.form.items()
            if k != "action"
        }

        # Prefer local processing for speed and predictable operation.
        # iLovePDF can be enabled as a primary provider with USE_ILOVEPDF=true.
        use_api = os.getenv("USE_ILOVEPDF", "false").lower() in {"1", "true", "yes"}
        api_error = None

        if use_api and ilovepdf_available():
            try:
                output = process_ilovepdf(action, uploaded, params, TMP_DIR)
            except Exception as exc:
                api_error = str(exc)

        if output is None:
            try:
                output = process_local(action, uploaded, params, TMP_DIR)
            except Exception as local_exc:
                # If local processing failed, try the API as a second chance.
                if ilovepdf_available() and not (use_api and api_error):
                    try:
                        output = process_ilovepdf(action, uploaded, params, TMP_DIR)
                    except Exception as api_exc:
                        raise ValueError(
                            f"Local processing failed: {local_exc}. "
                            f"API fallback failed: {api_exc}"
                        )
                elif api_error:
                    raise ValueError(
                        f"iLovePDF failed, then local fallback failed: {local_exc}. "
                        f"API error: {api_error}"
                    )
                else:
                    raise

        if isinstance(output, (list, tuple)):
            # Multiple outputs are packaged by the local/API service.
            output = output[0]

        output = Path(output)
        if not output.exists():
            raise ValueError("Processing finished but no output file was created.")

        return make_download(output)

    except Exception as exc:
        return jsonify({"error": str(exc)}), 400
    finally:
        # Keep output until the response is sent; cleanup_old_files removes it later.
        for p in uploaded:
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass


if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port, debug=False)
