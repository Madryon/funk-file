from pathlib import Path
import io
import math
import os
import shutil
import subprocess
import tempfile
import zipfile

from PIL import Image
from pypdf import PdfReader, PdfWriter, Transformation
from reportlab.pdfgen import canvas


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
PDF_EXTS = {".pdf"}
OFFICE_EXTS = {".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"}


def _reader(path, password=None):
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        if password:
            result = reader.decrypt(password)
        else:
            result = reader.decrypt("")
        if not result:
            raise ValueError("PDF is password protected. Enter the correct password.")
    return reader


def _output(tmp_dir, stem, suffix):
    p = Path(tmp_dir) / f"{stem}_{os.urandom(5).hex()}{suffix}"
    return p


def _write_pages(reader, indexes, out):
    writer = PdfWriter()
    for i in indexes:
        if i < 0 or i >= len(reader.pages):
            raise ValueError(f"Page {i + 1} is outside the document.")
        writer.add_page(reader.pages[i])
    if not writer.pages:
        raise ValueError("No pages selected.")
    with open(out, "wb") as f:
        writer.write(f)
    return out


def _parse_pages(spec, total):
    # Supports: 1,3,5-8 and also 8-5 by normalizing it.
    pages = []
    for token in (spec or "").split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            a, b = token.split("-", 1)
            start, end = int(a), int(b)
            if start > end:
                start, end = end, start
            if start < 1 or end > total:
                raise ValueError(f"Page range {token} is outside 1-{total}.")
            pages.extend(range(start - 1, end))
        else:
            n = int(token)
            if n < 1 or n > total:
                raise ValueError(f"Page {n} is outside 1-{total}.")
            pages.append(n - 1)
    # preserve order but remove duplicates
    return list(dict.fromkeys(pages))


def _images_to_pdf(paths, out):
    images = []
    for p in paths:
        img = Image.open(p).convert("RGB")
        images.append(img)
    if not images:
        raise ValueError("No images selected.")
    first, rest = images[0], images[1:]
    first.save(out, "PDF", save_all=True, append_images=rest, resolution=150.0)
    return out


def _pdf_to_images(src, out_dir, fmt):
    try:
        import pypdfium2 as pdfium
    except ImportError:
        raise ValueError("PDF image rendering dependency is unavailable.")

    out_dir = Path(out_dir)
    out_dir.mkdir(exist_ok=True)
    doc = pdfium.PdfDocument(str(src))
    paths = []
    for idx in range(len(doc)):
        page = doc[idx]
        bitmap = page.render(scale=150 / 72)
        image = bitmap.to_pil()
        if fmt == "jpg":
            image = image.convert("RGB")
        path = out_dir / f"page_{idx+1:04d}.{fmt}"
        image.save(path, "JPEG" if fmt == "jpg" else "PNG", quality=90 if fmt == "jpg" else None)
        paths.append(path)
    if not paths:
        raise ValueError("PDF has no pages.")
    return paths


def _zip(paths, out):
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in paths:
            z.write(p, Path(p).name)
    return out


def _compress_pdf(src, out, level):
    # Fast native optimization first. Rasterization is intentionally avoided
    # unless explicitly requested because it can destroy text/vector quality.
    reader = _reader(src)
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
        try:
            page.compress_content_streams()
        except Exception:
            pass
    with open(out, "wb") as f:
        writer.write(f)

    # If the native pass did not reduce the file, keep the valid optimized copy.
    return out


def _watermark(src, out, text, opacity=0.25, rotation=45):
    reader = _reader(src)
    writer = PdfWriter()
    for page in reader.pages:
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        packet = io.BytesIO()
        c = canvas.Canvas(packet, pagesize=(width, height))
        c.saveState()
        c.translate(width / 2, height / 2)
        c.rotate(rotation)
        c.setFillAlpha(max(0.05, min(1.0, opacity)))
        c.setFont("Helvetica-Bold", min(42, max(14, width / 12)))
        c.drawCentredString(0, 0, text)
        c.restoreState()
        c.save()
        packet.seek(0)
        wm = PdfReader(packet).pages[0]
        page.merge_page(wm, over=True)
        writer.add_page(page)
    with open(out, "wb") as f:
        writer.write(f)
    return out


def _protect(src, out, password):
    if not password:
        raise ValueError("Password is required.")
    reader = _reader(src)
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.encrypt(user_password=password, owner_password=password, use_128bit=True)
    with open(out, "wb") as f:
        writer.write(f)
    return out


def _unlock(src, out, password):
    reader = _reader(src, password)
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    with open(out, "wb") as f:
        writer.write(f)
    return out


def _rotate(src, out, degrees, pages_spec):
    reader = _reader(src)
    selected = set(_parse_pages(pages_spec, len(reader.pages))) if pages_spec else set(range(len(reader.pages)))
    writer = PdfWriter()
    for i, page in enumerate(reader.pages):
        if i in selected:
            page.rotate(degrees % 360)
        writer.add_page(page)
    with open(out, "wb") as f:
        writer.write(f)
    return out


def _office_to_pdf(src, out):
    # Optional local fallback if LibreOffice is installed on the host.
    soffice = shutil.which("libreoffice") or shutil.which("soffice")
    if not soffice:
        raise ValueError(
            "Word/Office to PDF needs iLovePDF API or LibreOffice. "
            "Add iLovePDF keys on Render for this conversion."
        )
    with tempfile.TemporaryDirectory() as td:
        cmd = [
            soffice, "--headless", "--convert-to", "pdf",
            "--outdir", td, str(src)
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=120)
        if result.returncode != 0:
            raise ValueError(result.stderr.decode(errors="ignore")[-1000:])
        generated = Path(td) / (src.stem + ".pdf")
        if not generated.exists():
            raise ValueError("Office conversion produced no PDF.")
        shutil.copy2(generated, out)
    return out


def process_local(action, files, params, tmp_dir):
    first = Path(files[0])
    ext = first.suffix.lower()
    stem = first.stem

    if action == "merge":
        writer = PdfWriter()
        for p in files:
            p = Path(p)
            if p.suffix.lower() in IMAGE_EXTS:
                tmp = _output(tmp_dir, p.stem, ".pdf")
                _images_to_pdf([p], tmp)
                p = tmp
            reader = _reader(p)
            for page in reader.pages:
                writer.add_page(page)
        out = _output(tmp_dir, "merged", ".pdf")
        with open(out, "wb") as f:
            writer.write(f)
        return out

    if action == "split":
        reader = _reader(first)
        total = len(reader.pages)
        mode = params.get("split_mode", "ranges")
        outputs = []
        if mode == "fixed":
            n = int(params.get("chunk_size", "1"))
            if n < 1:
                raise ValueError("Chunk size must be at least 1.")
            ranges = [(i, min(i + n, total)) for i in range(0, total, n)]
        else:
            idx = _parse_pages(params.get("pages"), total)
            # Convert selected page list into one PDF per comma-separated range.
            ranges = []
            for token in (params.get("pages") or "").split(","):
                token = token.strip()
                if not token:
                    continue
                token_pages = _parse_pages(token, total)
                if token_pages:
                    ranges.append((token_pages[0], token_pages[-1] + 1))
        if not ranges:
            raise ValueError("Enter page ranges such as 1-3,5-7 or choose fixed chunks.")
        for n, (a, b) in enumerate(ranges, 1):
            out = _output(tmp_dir, f"split_{n:02d}", ".pdf")
            _write_pages(reader, range(a, b), out)
            outputs.append(out)
        if len(outputs) == 1:
            return outputs[0]
        return _zip(outputs, _output(tmp_dir, "split_files", ".zip"))

    if action == "compress":
        return _compress_pdf(first, _output(tmp_dir, stem + "_compressed", ".pdf"), params.get("level", "recommended"))

    if action == "pdf-to-word":
        try:
            from pdf2docx import Converter
        except ImportError:
            raise ValueError("PDF-to-Word dependency is unavailable.")
        out = _output(tmp_dir, stem, ".docx")
        # Validate encryption first; pdf2docx handles layout conversion.
        _reader(first)
        cv = Converter(str(first))
        try:
            cv.convert(str(out))
        finally:
            cv.close()
        return out

    if action == "word-to-pdf":
        return _office_to_pdf(first, _output(tmp_dir, stem, ".pdf"))

    if action in {"pdf-to-jpg", "pdf-to-png"}:
        fmt = "jpg" if action.endswith("jpg") else "png"
        out_dir = Path(tmp_dir) / f"{stem}_{fmt}"
        paths = _pdf_to_images(first, out_dir, fmt)
        return paths[0] if len(paths) == 1 else _zip(paths, _output(tmp_dir, f"{stem}_{fmt}", ".zip"))

    if action in {"jpg-to-pdf", "png-to-pdf"}:
        return _images_to_pdf(files, _output(tmp_dir, "images", ".pdf"))

    if action == "rotate":
        deg = int(params.get("degrees", "90"))
        if deg not in {90, 180, 270}:
            raise ValueError("Rotation must be 90, 180, or 270 degrees.")
        return _rotate(first, _output(tmp_dir, stem + "_rotated", ".pdf"), deg, params.get("pages"))

    if action in {"delete-pages", "extract-pages"}:
        reader = _reader(first)
        selected = _parse_pages(params.get("pages"), len(reader.pages))
        if action == "delete-pages":
            keep = [i for i in range(len(reader.pages)) if i not in set(selected)]
        else:
            keep = selected
        if not keep:
            raise ValueError("The operation would produce an empty PDF.")
        return _write_pages(reader, keep, _output(tmp_dir, stem + ("_pages" if action == "extract-pages" else "_clean"), ".pdf"))

    if action == "watermark":
        return _watermark(
            first,
            _output(tmp_dir, stem + "_watermarked", ".pdf"),
            params.get("text", "CONFIDENTIAL"),
            float(params.get("opacity", "0.25")),
            int(params.get("rotation", "45")),
        )

    if action == "protect":
        return _protect(first, _output(tmp_dir, stem + "_protected", ".pdf"), params.get("password", ""))

    if action == "unlock":
        return _unlock(first, _output(tmp_dir, stem + "_unlocked", ".pdf"), params.get("password", ""))

    raise ValueError("Unsupported local operation.")
