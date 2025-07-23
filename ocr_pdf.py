import requests
import tempfile
from pdf2image import convert_from_path
import pytesseract
import os

# Thêm Poppler vào PATH
os.environ["PATH"] += os.pathsep + r"C:\Release-24.08.0-0\poppler-24.08.0\Library\bin"


def is_pdf(url_pdf):
    return url_pdf.lower().endswith('.pdf')

def ocr_pdf_from_url(pdf_url, lang="vie", max_chars=2000, max_pages=5):
    try:
        response = requests.get(pdf_url, stream=True, timeout=15)
        response.raise_for_status()

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_file:
            tmp_file.write(response.content)
            local_path = tmp_file.name

        # OCR từng trang PDF
        images = convert_from_path(local_path)
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