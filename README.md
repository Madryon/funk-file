# Funk File (This is old file you can check new file on - https://pdf-toolbox-3ph1.onrender.com/ )
A lightweight Flask PDF toolkit designed for GitHub + Render.

## Included tools

- Merge PDF
- Split PDF by ranges or fixed chunks
- Compress PDF
- PDF → Word
- Word/Office → PDF (iLovePDF or local LibreOffice)
- PDF → JPG
- PDF → PNG
- JPG → PDF
- PNG → PDF
- Rotate PDF
- Delete PDF pages
- Extract PDF pages
- Text watermark
- Password protect PDF
- Unlock PDF with a known password

## Design choices

The original CLI-style PDF engine was simplified into a web-first service. Video, QR and unrelated CLI features are intentionally left out of the web app so the Render deployment stays lighter and easier to maintain.

Local processing is preferred by default for speed and to avoid API dependency. If a local operation fails and iLovePDF credentials exist, the server can try the API as a fallback.

Set `USE_ILOVEPDF=true` if you want iLovePDF to be attempted first.

iLovePDF credentials are read from environment variables only. Never put them in GitHub.

## 50 MB limit

The Flask server rejects requests above `MAX_UPLOAD_MB` (default 50 MB).

## Run locally

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

macOS/Linux:

```bash
source .venv/bin/activate
```

Then:

```bash
pip install -r requirements.txt
python app.py
```

Open:

```text
http://127.0.0.1:10000
```

## Render deployment

1. Create a GitHub repository.
2. Upload this folder.
3. In Render, choose **New → Web Service** and connect the repository.
4. Render can use `render.yaml`, or manually set:
   - Build: `pip install -r requirements.txt`
   - Start: `gunicorn app:app --workers 1 --threads 4 --timeout 180`
5. Add environment variables if using iLovePDF:
   - `ILOVEPDF_PUBLIC_KEY`
   - `ILOVEPDF_SECRET_KEY`
   - `USE_ILOVEPDF=true` (optional)

The secret key must remain a Render environment variable, never frontend JavaScript and never a committed file.

## Future login + database

You do **not** need to add login/database now.

The project is deliberately split into:
- `app.py` — HTTP routes
- `services/local_pdf.py` — PDF operations
- `services/ilovepdf_api.py` — optional external provider
- `templates/` — HTML
- `static/css/` — CSS
- `static/js/` — browser JavaScript

That separation makes a future upgrade straightforward. Later we can add:
- Flask-Login/Auth provider
- PostgreSQL
- User profiles
- Processing history
- Saved files/metadata
- Usage quotas
- Admin dashboard

For persistent history, files should eventually move from temporary Render storage to object storage (for example S3-compatible storage), because a Render web service should not be treated as permanent file storage.

## Privacy / cleanup

Uploaded files are stored in the app's temporary directory while processing. Old temporary files are automatically deleted when cleanup runs.

## Important limitation

PDF → Word is best for digitally generated PDFs. Scanned/image-only PDFs may need OCR for high-quality editable text.

Word/Office → PDF needs iLovePDF or a server with LibreOffice installed. For the easiest Render deployment, configure iLovePDF keys for this conversion.

## iLovePDF

The optional integration follows iLovePDF's task workflow: start a task, upload files, process, then download the result. Their current REST API documentation also states that the secret key must not be exposed client-side.

Official docs:
- https://developer.ilovepdf.com/docs
