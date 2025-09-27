import io
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
from starlette.responses import Response

app = FastAPI(title="Image Converter API")

origins = [
    "http://localhost:5173",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

@app.post("/convert/", tags=["Image Conversion"])
async def convert_image(
    file: UploadFile = File(..., description="Image file to be converted."), 
    target_format: str = Form(..., description="Target format (e.g., webp, jpeg, ico)."),
    output_filename: str = Form(None, description="Optional desired output filename (without extension).")
):

    supported_formats = {
        "webp": "WEBP", "jpeg": "JPEG", "png": "PNG",
        "ico": "ICO", "gif": "GIF"
    }
    
    if target_format.lower() not in supported_formats:
        raise HTTPException(status_code=400, detail=f"Target format '{target_format}' is not supported.")

    try:
        contents = await file.read()
        img = Image.open(io.BytesIO(contents))
        output_buffer = io.BytesIO()

        format_key = target_format.lower()
        pil_format = supported_formats[format_key]

        if img.mode in ['RGBA', 'LA'] and format_key in ['jpeg']:
            img = img.convert('RGB')
        
        if format_key == 'ico':
            img.save(output_buffer, format=pil_format, sizes=[(16,16), (32,32), (48,48), (64,64)])
        else:
            img.save(output_buffer, format=pil_format, quality=85)
        
        output_buffer.seek(0)
        
        if output_filename:
            clean_filename = "".join(c for c in output_filename if c.isalnum() or c in (' ', '_', '-')).rstrip()
            new_filename = f"{clean_filename or 'converted'}.{format_key}"
        else:
            original_name = file.filename.rsplit('.', 1)[0]
            new_filename = f"{original_name}.{format_key}"
        
        headers = {'Content-Disposition': f'attachment; filename="{new_filename}"'}

        return Response(
            content=output_buffer.getvalue(), 
            media_type=f"image/{format_key}",
            headers=headers
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred during conversion: {str(e)}")

@app.get("/", tags=["Root"])
async def read_root():
    return {"status": "ok", "message": "Welcome to the Image Converter API!"}