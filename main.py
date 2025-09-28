import io
import os
import re
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
from starlette.responses import Response

load_dotenv()

RECAPTCHA_SECRET_KEY = os.getenv("RECAPTCHA_SECRET_KEY")
if not RECAPTCHA_SECRET_KEY:
    raise RuntimeError("RECAPTCHA_SECRET_KEY not set in environment variables (.env)")

RECAPTCHA_V3_THRESHOLD = float(os.getenv("RECAPTCHA_V3_THRESHOLD", "0.3"))

app = FastAPI(title="Image Converter API")

origins = [
    "http://localhost:5173",
    "http://localhost:3000",
    "https://converter.innovixus.my.id",
    "https://innovixus.my.id",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


async def verify_recaptcha(token: str) -> dict:
    url = "https://www.google.com/recaptcha/api/siteverify"
    payload = {"secret": RECAPTCHA_SECRET_KEY, "response": token}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(url, data=payload)
        resp.raise_for_status()
        return resp.json()


def sanitize_filename(name: str, ext: str) -> str:
    if "." in name:
        name = name.rsplit(".", 1)[0]
    clean = re.sub(r'[^A-Za-z0-9 _\-]', "", name).strip()
    if not clean:
        clean = "converted"
    return f"{clean}.{ext}"


@app.post("/convert/", tags=["Image Conversion"])
async def convert_image(
    file: UploadFile = File(...),
    target_format: str = Form(...),
    output_filename: str | None = Form(None),
    g_recaptcha_response: str = Form(..., alias="g-recaptcha-response"),
):

    try:
        recaptcha_result = await verify_recaptcha(g_recaptcha_response)
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Gagal memverifikasi reCAPTCHA (network).")

    if not recaptcha_result.get("success", False):
        codes = recaptcha_result.get("error-codes", [])
        raise HTTPException(status_code=400, detail=f"reCAPTCHA validation failed. {codes}")

    score = recaptcha_result.get("score")
    if score is not None:
        try:
            score = float(score)
        except Exception:
            score = None
        if score is not None and score < RECAPTCHA_V3_THRESHOLD:
            raise HTTPException(status_code=400, detail=f"reCAPTCHA score too low ({score}).")

    supported_formats = {
        "webp": "WEBP",
        "jpeg": "JPEG",
        "png": "PNG",
        "ico": "ICO",
        "gif": "GIF",
    }
    format_key = target_format.lower()
    if format_key not in supported_formats:
        raise HTTPException(status_code=400, detail=f"Target format '{target_format}' is not supported.")

    try:
        contents = await file.read()
        img = Image.open(io.BytesIO(contents))
        output_buffer = io.BytesIO()

        pil_format = supported_formats[format_key]

        if img.mode in ("RGBA", "LA") and format_key in ("jpeg", "jpg"):
            img = img.convert("RGB")

        if format_key == "ico":
            img.save(output_buffer, format=pil_format, sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
        else:
            if pil_format == "JPEG":
                img.save(output_buffer, format=pil_format, quality=85)
            else:
                img.save(output_buffer, format=pil_format)

        output_buffer.seek(0)

        if output_filename and output_filename.strip():
            new_filename = sanitize_filename(output_filename, format_key)
        else:
            original_name = (file.filename or "converted").rsplit(".", 1)[0]
            new_filename = sanitize_filename(original_name, format_key)

        headers = {"Content-Disposition": f'attachment; filename="{new_filename}"'}

        return Response(content=output_buffer.getvalue(), media_type=f"image/{format_key}", headers=headers)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred during conversion: {str(e)}")
