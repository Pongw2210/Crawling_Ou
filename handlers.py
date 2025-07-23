from bs4 import BeautifulSoup
from readability import Document
from selenium.webdriver.common.devtools.v136.network import delete_cookies
from six import reraise

def handler_model_ou_main(html):
    soup = BeautifulSoup(html, "html.parser")
    content_div = soup.select_one("div.content")  # Tìm thẻ div có class "content"

    if not content_div:
        return None

    title_tag = content_div.select_one("h3.title")
    paragraphs = content_div.select("div.small p")

    if not title_tag or not paragraphs:
        return None

    title = title_tag.get_text(strip=True)
    content = '\n'.join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))

    return title, content, "Ou Main"


def handler_model_elementor_event(html):
    soup = BeautifulSoup(html, "html.parser")
    title_tag = soup.select_one("h2.elementor-heading-title")

    if not title_tag:
        return None

    paragraphs = soup.select("div.elementor-widget-container p")
    title = title_tag.get_text(strip=True)
    content = '\n'.join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))

    return title,content,"Elementor"


from bs4 import BeautifulSoup

def handler_model_it_ou(html):
    soup = BeautifulSoup(html, "html.parser")
    # Chọn đúng div chứa nội dung bài viết
    content_div = soup.select_one("div.fp-leftpad.content-inner")

    if content_div:
        title_tag = content_div.select_one("h4.clr-b")
        title = title_tag.get_text(strip=True) if title_tag else ""

        # Lọc span cấp ngoài cùng, tránh span con lặp nội dung
        spans = [
            span for span in content_div.select("span")
            if not span.find_parent("span") and span.get_text(strip=True)
        ]
        content_lines = [span.get_text(strip=True) for span in spans]
        content = "\n".join(content_lines)

        return title, content, "IT OU"
    return None

def handle_model_readability(html):
    try:
        doc = Document(html)
        title = doc.short_title()
        content = BeautifulSoup(doc.summary(),"html.parser").get_text('\n',strip=True)
        if title or content:
            return title,content,"Readability"
    except:
        pass
    return None

def handle_fallback(html):
    soup = BeautifulSoup(html, "html.parser")
    text = soup.body.get_text(separator="\n", strip=True) if soup.body else ""
    return "", text[:300], "Fallback"

