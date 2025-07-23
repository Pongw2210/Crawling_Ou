import requests
from PIL import Image
from io import BytesIO
import pytesseract

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

def is_image(url_image):
    return any(url_image.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.bmp'])

def ocr_image_from_url(img_url, lang="vie"):
    try:
        response = requests.get(img_url, timeout=10)
        response.raise_for_status()  # Đảm bảo URL hợp lệ
        img = Image.open(BytesIO(response.content)).convert("RGB")
        text = pytesseract.image_to_string(img, lang=lang)
        return text.strip()
    except Exception as e:
        print(f"OCR ảnh lỗi: {img_url} - {e}")
        return ""
