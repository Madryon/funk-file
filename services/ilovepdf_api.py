"""
iLovePDF API provider for Funk File.

Uses the official iLovePDF Python SDK.
API keys are read only from environment variables.

If an iLovePDF operation fails, app.py can fall back
to the local PDF processor where supported.
"""

import os
import zipfile
from pathlib import Path


def ilovepdf_available():
    """Return True when both iLovePDF API keys are configured."""
    return bool(
        os.getenv("ILOVEPDF_PUBLIC_KEY")
        and os.getenv("ILOVEPDF_SECRET_KEY")
    )


def process_ilovepdf(action, files, params, tmp_dir):
    """
    Process a PDF operation using the iLovePDF Python SDK.

    Parameters:
        action: Funk File action name
        files: list of Path objects
        params: dictionary of operation parameters
        tmp_dir: temporary working directory

    Returns:
        Path to the downloaded output file.
    """

    try:
        from ilovepdf import (
            CompressTask,
            MergeTask,
            SplitTask,
            OfficePdfTask,
            PdfToJpgTask,
            ImagePdfTask,
            RotateTask,
            ProtectTask,
            UnlockTask,
            WatermarkTask,
            ExtractTask,
        )
    except ImportError as exc:
        raise RuntimeError(
            "The iLovePDF Python SDK is not installed."
        ) from exc

    public = os.environ.get("ILOVEPDF_PUBLIC_KEY")
    secret = os.environ.get("ILOVEPDF_SECRET_KEY")

    if not public or not secret:
        raise RuntimeError(
            "iLovePDF API keys are missing. "
            "Add ILOVEPDF_PUBLIC_KEY and ILOVEPDF_SECRET_KEY "
            "to the environment variables."
        )

    # Map Funk File actions to official iLovePDF Python task classes.
    task_classes = {
        "merge": MergeTask,
        "split": SplitTask,
        "compress": CompressTask,
        "word-to-pdf": OfficePdfTask,
        "pdf-to-jpg": PdfToJpgTask,
        "jpg-to-pdf": ImagePdfTask,
        "png-to-pdf": ImagePdfTask,
        "rotate": RotateTask,
        "extract-pages": ExtractTask,
        "watermark": WatermarkTask,
        "protect": ProtectTask,
        "unlock": UnlockTask,
    }

    task_class = task_classes.get(action)

    if task_class is None:
        raise RuntimeError(
            f"iLovePDF API does not currently handle action: {action}"
        )

    # Create the task directly.
    task = task_class(
        public_key=public,
        secret_key=secret
    )

    # Add uploaded files.
    for file_path in files:
        task.add_file(str(file_path))

    # -------------------------
    # Task-specific parameters
    # -------------------------

    if action == "compress":
        level = params.get("level", "recommended")

        try:
            task.compression_level = level
        except Exception:
            pass

    elif action == "split":
        mode = params.get("split_mode", "ranges")

        if mode == "fixed":
            try:
                task.fixed_range = int(
                    params.get("chunk_size", "1")
                )
            except (TypeError, ValueError):
                task.fixed_range = 1

        else:
            task.ranges = params.get("pages", "")

    elif action == "extract-pages":
        task.ranges = params.get("pages", "")

    elif action == "protect":
        task.password = params.get("password", "")

    elif action == "watermark":
        task.text = params.get(
            "text",
            "CONFIDENTIAL"
        )

        try:
            opacity = float(
                params.get("opacity", "0.25")
            )
        except (TypeError, ValueError):
            opacity = 0.25

        # iLovePDF uses transparency rather than opacity.
        transparency = int(
            max(0, min(100, (1 - opacity) * 100))
        )

        task.transparency = transparency

        try:
            task.rotation = int(
                params.get("rotation", "45")
            )
        except (TypeError, ValueError):
            task.rotation = 45

    elif action == "rotate":
        try:
            degrees = int(
                params.get("degrees", "90")
            )
        except (TypeError, ValueError):
            degrees = 90

        task.rotation = degrees

    elif action == "delete-pages":
        # This action is better handled locally.
        raise RuntimeError(
            "Delete pages is handled by the local PDF processor."
        )

    elif action == "pdf-to-png":
        # iLovePDF's PDF-to-JPG task produces JPG.
        # PNG is handled locally to preserve PNG output.
        raise RuntimeError(
            "PDF to PNG is handled by the local PDF processor."
        )

    elif action == "pdf-to-word":
        # Keep PDF to Word on the local processor for now.
        # This avoids using an unsupported SDK task name.
        raise RuntimeError(
            "PDF to Word is handled by the local PDF processor."
        )

    # -------------------------
    # Execute iLovePDF task
    # -------------------------

    try:
        task.execute()
    except Exception as exc:
        raise RuntimeError(
            f"iLovePDF task failed: {exc}"
        ) from exc

    # -------------------------
    # Download result
    # -------------------------

    out_dir = Path(tmp_dir) / "ilovepdf_output"
    out_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    try:
        result = task.download(str(out_dir))
    except Exception as exc:
        raise RuntimeError(
            f"iLovePDF output download failed: {exc}"
        ) from exc

    # If SDK returns an output path.
    if result:
        result_path = Path(result)

        if result_path.exists() and result_path.is_file():
            return result_path

    # Otherwise find generated files.
    output_files = sorted(
        p for p in out_dir.rglob("*")
        if p.is_file()
    )

    if not output_files:
        raise RuntimeError(
            "iLovePDF completed but no output file was found."
        )

    # Single output file.
    if len(output_files) == 1:
        return output_files[0]

    # Multiple output files -> ZIP them.
    zip_path = Path(tmp_dir) / "ilovepdf_result.zip"

    with zipfile.ZipFile(
        zip_path,
        "w",
        zipfile.ZIP_DEFLATED
    ) as archive:

        for file_path in output_files:
            archive.write(
                file_path,
                file_path.name
            )

    return zip_path
