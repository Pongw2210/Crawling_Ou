from bs4 import BeautifulSoup

from ocr_pdf import is_pdf, ocr_pdf_from_url
from ocr_image import is_image,ocr_image_from_url
from urllib.parse import urljoin
from handlers import handler_model_ou_main, handler_model_elementor_event,handler_model_it_ou,handle_model_readability,handle_fallback

def extract_pdf_content(soup, base_url,original_content):
    pdf_links = set()  # Dùng set để tránh trùng link, tự động loại trùng
    content = ""

    for tag in soup.find_all("a", href=True):
        href = tag["href"]
        if is_pdf(href):
            full_pdf_url = urljoin(base_url, href)
            pdf_links.add(full_pdf_url)

    for pdf_url in pdf_links:
        # print(f"OCR PDF: {pdf_url}")
        pdf_text = ocr_pdf_from_url(pdf_url)
        if pdf_text and pdf_text not in original_content:
            content += f"\n\n--- Nội dung từ PDF ({pdf_url}) ---\n{pdf_text}"

    return content

def extract_img_content(soup, base_url, original_content):
    img_links = set()
    content = ""

    content_blocks = soup.select("div.content, div.article, .post-content, .fp-leftpad.content-inner")
    for block in content_blocks:
        for img_tag in block.find_all("img", src=True):
            img_src = img_tag.get('src')
            if is_image(img_src):
                full_img_url = urljoin(base_url, img_src)
                img_links.add(full_img_url)

    for img_url in img_links:
        # print(f"OCR IMAGE: {img_url}")
        img_text = ocr_image_from_url(img_url)
        if img_text and img_text not in original_content:
            content += f"\n\n--- Nội dung từ ảnh ({img_url}) ---\n{img_text}"

    return content

def extract_flexible_content(html, base_url):
    handlers = [
        handler_model_it_ou,
        handler_model_ou_main,
        handler_model_elementor_event,
        handle_model_readability,
        handle_fallback
    ]

    for handler in handlers:
        result = handler(html)
        if result:
            title, content, model = result

            soup = BeautifulSoup(html, "html.parser")

            content += extract_pdf_content(soup,base_url,content)
            content += extract_img_content(soup,base_url,content)

            return title, content, model

    return "", "", "No Match"