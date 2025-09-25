import os
import platform
import requests
import tempfile
from io import BytesIO
from PIL import Image
import pytesseract
from pdf2image import convert_from_path

# Detect OS để set path cho Tesseract và Poppler
if platform.system() == "Windows":
    # Windows: chỉ định path cài đặt Tesseract và Poppler
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    poppler_path = r"C:\Release-24.08.0-0\poppler-24.08.0\Library\bin"
else:
    # Linux / Colab: dùng bản cài qua apt-get
    pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"
    poppler_path = None  # trên Linux không cần chỉ định


# ================== IMAGE OCR ==================

def is_image(url_image):
    return any(url_image.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".bmp", ".gif"])


def ocr_image_from_url(img_url, lang="vie"):
    try:
        response = requests.get(img_url, timeout=10)
        response.raise_for_status()
        img = Image.open(BytesIO(response.content)).convert("RGB")
        text = pytesseract.image_to_string(img, lang=lang)
        return text.strip()
    except Exception as e:
        print(f"OCR ảnh lỗi: {img_url} - {e}")
        return ""


# ================== PDF OCR ==================

def is_pdf(url_pdf):
    return url_pdf.lower().endswith(".pdf")


def ocr_pdf_from_url(pdf_url, lang="vie", max_chars=2000, max_pages=5):
    try:
        response = requests.get(pdf_url, stream=True, timeout=15)
        response.raise_for_status()

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_file:
            tmp_file.write(response.content)
            local_path = tmp_file.name

        images = convert_from_path(local_path, poppler_path=poppler_path)
        full_text = ""

        for i, img in enumerate(images):
            if max_pages is not None and i >= max_pages:
                full_text += f"\n... (Chỉ OCR {max_pages} trang đầu)"
                break

            text = pytesseract.image_to_string(img, lang=lang)
            full_text += f"\n--- Trang {i + 1} ---\n{text.strip()}"

        os.remove(local_path)

        if max_chars is not None:
            return full_text.strip()[:max_chars]
        return full_text.strip()

    except Exception as e:
        print(f"OCR PDF lỗi: {pdf_url} - {e}")
        return ""
