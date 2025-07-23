import csv
import os
import pickle
import time

from config import driver
from urllib.parse import urlparse, urljoin
from extract_content import extract_flexible_content
from bs4 import BeautifulSoup

class FullSmartCrawler:
    def __init__(self, start_url, limit=None, max_duration=None,driver=None):
        self.start_url = start_url
        self.start_netloc = urlparse(start_url).netloc
        self.to_visit = set([start_url])
        self.visited = set()
        self.results = []  # chứa các dict {'title', 'href', 'content'}
        self.limit = limit
        self.max_duration = max_duration
        self.driver = driver

    def quit_driver(self):
        if self.driver:
            self.driver.quit()

    def save_state(self, filename='crawler_state.pkl'):
        with open(filename, 'wb') as f:
            pickle.dump({
                'visited': self.visited,
                'to_visit': self.to_visit
            }, f)
        print(f"(Save_State) Đã lưu trạng thái crawl vào {filename}")

    def load_state(self, filename='crawler_state.pkl'):
        if os.path.exists(filename):
            with open(filename, 'rb') as f:
                state = pickle.load(f)
                self.visited = state.get('visited', set())
                self.to_visit = state.get('to_visit', set())
            print(f"(Load_State) Đã khôi phục trạng thái từ {filename}")
        else:
            print(f"(Load_State) Không tìm thấy {filename}")

    def save_csv(self, filename):
        with open(filename, 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=['title', 'href', 'content'])
            writer.writeheader()
            for row in self.results:
                writer.writerow(row)
        print(f"Đã lưu kết quả vào {filename}")

    def is_ou_domain(self, netloc):
        return netloc == "ou.edu.vn" or netloc.endswith(".ou.edu.vn")

    def run(self):
        start_time = time.time()

        print(f"(Check) to_visit: {len(self.to_visit)} | visited: {len(self.visited)}")
        print(f"(Check) URL đầu tiên chuẩn bị xử lý: {list(self.to_visit)[:1]}")

        while self.to_visit:
            if self.limit and len(self.results) >= self.limit:
                print(f"(Run) Đạt giới hạn {self.limit} kết quả. Dừng crawl.")
                break

            if self.max_duration and (time.time() - start_time) >= self.max_duration:
                print(f"(Run) Hết thời gian giới hạn {self.max_duration} giây. Dừng và lưu trạng thái.")
                self.save_state()
                self.save_csv('ou_output.csv')
                break

            current_url = self.to_visit.pop()
            if current_url in self.visited:
                continue

            self.visited.add(current_url)
            print(f"[{len(self.results)} kết quả, {len(self.to_visit)} chờ] Đang xử lý: {current_url}")

            try:
                self.driver.get(current_url)
                html = self.driver.page_source
                title = ''
                content = ''

                title,content,model = extract_flexible_content(html,current_url)

                if title and content:
                    print("======= Đã trích xuất được:")
                    print("======= Title:", title)
                    print("======= Href :", current_url)
                    print("======= Content rút gọn:", content[:300].replace('\n', ' ') + '...')  # In 300 ký tự đ

                    self.results.append({
                        "title": title,
                        "href":current_url,
                        "content":content[:3000]
                    })

                soup = BeautifulSoup(html,"html.parser")
                for link_tag in soup.find_all('a',href=True):
                    href = link_tag['href']
                    full_url = urljoin(current_url,href)
                    netloc = urlparse(full_url).netloc

                    if self.is_ou_domain(netloc) and full_url not in self.visited and full_url not in self.to_visit:
                        self.to_visit.add(full_url)

            except Exception as e:
                print(f"(Lỗi) Khi xử lý {current_url}: {e}")
                continue

        print(f"Hoàn tất crawl: {len(self.results)} mục trong {(time.time() - start_time):.2f} giây.")
        return self.results

    def run_loop(self, interval=900, pause=10):
        while True:
            print(f"\nBắt đầu phiên crawl mới (tối đa {interval} giây)")
            self.max_duration = interval
            self.run()
            self.save_state()
            # self.save_csv("ou_output.csv")
            print(f"Tạm dừng {pause} giây trước phiên kế tiếp...\n")
            time.sleep(pause)

#=====================================================================
if __name__ == "__main__":
    crawler = FullSmartCrawler(
        start_url="https://ou.edu.vn",
        driver=driver
    )
    try:
        crawler.load_state()            # phục hồi trạng thái nếu có
        crawler.run_loop()                   # chạy crawl
    finally:
        crawler.quit_driver()


