"""
Optional iLovePDF REST API provider.

The app does not require API keys for local PDF operations. If keys are added
to Render/local .env, this provider can be used as a primary provider or
fallback. Secrets are read only from environment variables.
"""
import os
from pathlib import Path


def ilovepdf_available():
    return bool(
        os.getenv("ILOVEPDF_PUBLIC_KEY") and
        os.getenv("ILOVEPDF_SECRET_KEY")
    )


def process_ilovepdf(action, files, params, tmp_dir):
    try:
        from ilovepdf import Ilovepdf
    except ImportError as exc:
        raise RuntimeError("The optional iLovePDF Python SDK is not installed.") from exc

    public = os.environ["ILOVEPDF_PUBLIC_KEY"]
    secret = os.environ["ILOVEPDF_SECRET_KEY"]

    tool_map = {
        "merge": "merge",
        "split": "split",
        "compress": "compress",
        "pdf-to-word": "pdftoword",
        "word-to-pdf": "officepdf",
        "pdf-to-jpg": "pdfjpg",
        "pdf-to-png": "pdfjpg",
        "jpg-to-pdf": "imagepdf",
        "png-to-pdf": "imagepdf",
        "rotate": "rotate",
        "delete-pages": "split",
        "extract-pages": "extract",
        "watermark": "watermark",
        "protect": "protect",
        "unlock": "unlock",
    }
    tool = tool_map.get(action)
    if not tool:
        raise ValueError(f"No iLovePDF mapping for {action}.")

    api = Ilovepdf(public, secret)
    task = api.new_task(tool)

    # Official SDKs use add_file + task-level attributes/process parameters.
    for p in files:
        task.add_file(str(p))

    extra = {}
    if action == "compress":
        extra["compression_level"] = params.get("level", "recommended")
    elif action == "split":
        mode = params.get("split_mode", "ranges")
        if mode == "fixed":
            extra["fixed_range"] = int(params.get("chunk_size", "1"))
        else:
            extra["ranges"] = params.get("pages", "")
    elif action == "delete-pages":
        extra["remove_pages"] = params.get("pages", "")
    elif action == "extract-pages":
        extra["ranges"] = params.get("pages", "")
    elif action == "protect":
        extra["password"] = params.get("password", "")
    elif action == "watermark":
        extra["text"] = params.get("text", "CONFIDENTIAL")
        extra["transparency"] = max(0, min(100, int((1 - float(params.get("opacity", "0.25"))) * 100)))
        extra["rotation"] = int(params.get("rotation", "45"))

    # The SDK's current Python API exposes execute() for task processing.
    # Set supported attributes when available, then execute/download.
    for key, value in extra.items():
        try:
            setattr(task, key, value)
        except Exception:
            pass

    if action in {"rotate"}:
        degrees = int(params.get("degrees", "90"))
        for p in getattr(task, "files", []) or []:
            try:
                p.rotate = degrees
            except Exception:
                pass

    task.execute()
    out_dir = Path(tmp_dir) / "ilovepdf_output"
    out_dir.mkdir(exist_ok=True)
    result = task.download(str(out_dir))

    if result:
        result_path = Path(result)
        if result_path.exists():
            return result_path

    candidates = sorted(out_dir.rglob("*"))
    files_out = [p for p in candidates if p.is_file()]
    if not files_out:
        raise RuntimeError("iLovePDF completed without a downloadable output.")
    if len(files_out) == 1:
        return files_out[0]

    import zipfile
    zip_path = Path(tmp_dir) / "ilovepdf_result.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files_out:
            z.write(p, p.name)
    return zip_path
