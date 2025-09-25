import os
import pickle
import time
import threading
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, urljoin
from queue import Queue, Empty

from config import create_driver
from extract_content import extract_flexible_content
from bs4 import BeautifulSoup


class FullSmartCrawler:
    def __init__(self, start_url, db_file="ou_output.db", limit=None, max_duration=None, max_workers=5):
        self.start_url = start_url
        self.start_netloc = urlparse(start_url).netloc
        self.to_visit = Queue()
        self.to_visit.put(start_url)

        self.visited = set()
        self.visited_lock = threading.Lock()

        self.results = []
        self.limit = limit
        self.max_duration = max_duration
        self.max_workers = max_workers

        self.active_threads = 0
        self.active_lock = threading.Lock()
        self.start_time = None

        # SQLite
        self.db_file = db_file
        self.db_lock = threading.Lock()
        self.init_db()

    # ------------------- SQLite -------------------
    def init_db(self):
        conn = sqlite3.connect(self.db_file, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                href TEXT UNIQUE,
                content TEXT
            )
        """)
        conn.commit()
        conn.close()
        print(f"(DB) Đã khởi tạo DB {self.db_file}")

    def save_row_sqlite(self, row):
        with self.db_lock:
            conn = sqlite3.connect(self.db_file, check_same_thread=False)
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "INSERT OR IGNORE INTO pages (title, href, content) VALUES (?, ?, ?)",
                    (row["title"], row["href"], row["content"])
                )
                conn.commit()
                print(f"\033[90m(DB) Đã lưu: {row['title'][:50]}... | {row['href']} | {row['content'][:300]}...\033[0m")
            except Exception as e:
                print(f"(DB Error) {e}")
            finally:
                conn.close()

    # ------------------- State save/load -------------------
    def save_state(self, filename="crawler_state.pkl"):
        with self.visited_lock:
            state = {
                "visited": self.visited,
                "to_visit": list(self.to_visit.queue),
            }
        with open(filename, "wb") as f:
            pickle.dump(state, f)
        print(f"(Save_State) Đã lưu trạng thái vào {filename}")

    def load_state(self, filename="crawler_state.pkl"):
        if os.path.exists(filename):
            with open(filename, "rb") as f:
                state = pickle.load(f)
                with self.visited_lock:
                    self.visited = state.get("visited", set())
                    to_visit_list = state.get("to_visit", [])
                    self.to_visit = Queue()
                    for url in to_visit_list:
                        self.to_visit.put(url)
            print(f"(Load_State) Đã khôi phục từ {filename}")
        else:
            print(f"(Load_State) Không tìm thấy {filename}")

    # ------------------- Kiểm tra domain -------------------
    def is_ou_domain(self, netloc):
        return netloc == "ou.edu.vn" or netloc.endswith(".ou.edu.vn")

    # ------------------- Xử lý URL -------------------
    def process_url(self, url):
        print(f"[Thread-{threading.current_thread().name}] Crawling: {url}")
        driver = create_driver()
        try:
            driver.get(url)
            current_url = driver.current_url
            html = driver.page_source

            title, content, model = extract_flexible_content(html, current_url)
            result = None
            if title and content:
                result = {
                    "title": title,
                    "href": current_url,
                    "content": content,
                }

            # Tìm link mới
            soup = BeautifulSoup(html, "html.parser")
            new_urls = []
            for tag in soup.find_all("a", href=True):
                full_url = urljoin(current_url, tag["href"])
                netloc = urlparse(full_url).netloc
                if self.is_ou_domain(netloc):
                    with self.visited_lock:
                        if full_url not in self.visited:
                            new_urls.append(full_url)
            return result, new_urls

        except Exception as e:
            print(f"(Error) {url}: {e}")
            return None, []
        finally:
            driver.quit()

    # ------------------- Worker -------------------
    def worker(self):
        with self.active_lock:
            self.active_threads += 1

        try:
            while True:
                if self.limit and len(self.results) >= self.limit:
                    break
                if self.max_duration and (time.time() - self.start_time) >= self.max_duration:
                    break

                try:
                    url = self.to_visit.get(timeout=5)
                except Empty:
                    with self.active_lock:
                        if self.active_threads <= 1:
                            break
                    continue

                with self.visited_lock:
                    if url in self.visited:
                        self.to_visit.task_done()
                        continue
                    self.visited.add(url)

                result, new_urls = self.process_url(url)

                if result:
                    self.save_row_sqlite(result)
                    with threading.Lock():
                        self.results.append(result)

                for new_url in new_urls:
                    with self.visited_lock:
                        if new_url not in self.visited:
                            self.to_visit.put(new_url)

                self.to_visit.task_done()

                with self.visited_lock, self.active_lock:
                    total_known = len(self.visited) + self.to_visit.qsize()
                    progress = (len(self.visited) / total_known * 100) if total_known else 0
                    print(
                        f"\033[92m[Debug] Visited={len(self.visited)} | "
                        f"Results={len(self.results)} | "
                        f"Queue={self.to_visit.qsize()} | "
                        f"ActiveThreads={self.active_threads} | "
                        f"Progress={progress:.2f}%\033[0m"
                    )

        finally:
            with self.active_lock:
                self.active_threads -= 1

    # ------------------- Run -------------------
    def run(self):
        self.start_time = time.time()
        print(f"(Start) to_visit={self.to_visit.qsize()} | visited={len(self.visited)}")

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [executor.submit(self.worker) for _ in range(self.max_workers)]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    print(f"(Worker error) {e}")

        print(
            f"\033[92m(Done) Collected {len(self.results)} pages "
            f"| Visited={len(self.visited)} "
            f"| Queue còn={self.to_visit.qsize()} "
            f"in {(time.time() - self.start_time):.2f}s\033[0m"
        )
        return self.results

    # ------------------- Loop crawl -------------------
    def run_loop(self, interval=100, pause=10):
        while True:
            if self.to_visit.empty():
                print("(Run_Loop) Hết URL để crawl.")
                break

            print(f"\n(Phiên mới) Crawl tối đa {interval} giây")
            self.max_duration = interval
            self.run()
            self.save_state()
            print(f"Tạm dừng {pause} giây...\n")
            time.sleep(pause)


if __name__ == "__main__":
    crawler = FullSmartCrawler(
        start_url="https://ou.edu.vn",
        max_workers=5
    )
    try:
        crawler.load_state()
        crawler.run_loop()
    except KeyboardInterrupt:
        print("Dừng bằng tay (Ctrl+C).")
