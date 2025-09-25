# import csv
# from bs4 import BeautifulSoup
# from urllib.parse import urljoin
#
# from config import driver
# from extract_content import extract_flexible_content
# from ocr_utils import is_pdf, ocr_pdf_from_url, is_image, ocr_image_from_url
#
# # --- Hàm lưu CSV ---
# def save_to_csv(filename, rows):
#     """Ghi dữ liệu vào file CSV"""
#     with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
#         fieldnames = ['title', 'content', 'href']
#         writer = csv.DictWriter(f, fieldnames=fieldnames)
#         writer.writeheader()
#         for row in rows:
#             writer.writerow(row)
#     print(f"Đã lưu {len(rows)} dòng vào {filename}")
#
# # --- Crawl 1 trang thử ---
# url = "http://it.ou.edu.vn/news/view/1297-thong-bao:-ke-hoach-thuc-tap-tot-nghiep-hoc-ky-1-nam-hoc-2025-%E2%80%93-2026-(chuong-trinh-chuan)"
# driver.get(url)
# html = driver.page_source
#
# # --- Lấy content ---
# title, content, model = extract_flexible_content(html, url)
# print("Mẫu handler:", model)
# print("Tiêu đề:", title)
# print("Nội dung preview:", content[:1000])
#
# # --- Lưu CSV ---
# all_rows = [{
#     "title": title,
#     "content": content,
#     "href": url,
# }]
#
# save_to_csv("test_crawl_chunks.csv", all_rows)
print("\033[97mThis is red text\033[0m")