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
    def __init__(self, start_url, db_file="ou_output.db", limit=None, max_duration=None, max_workers=3):
        self.start_url = start_url
        self.start_netloc = urlparse(start_url).netloc

        # queue urls
        self.to_visit = Queue()
        self.to_visit.put(start_url)

        # visited set + lock
        self.visited = set()
        self.visited_lock = threading.Lock()

        # results in-memory (optional)
        self.results = []
        self.result_lock = threading.Lock()

        # limits
        self.limit = limit
        self.max_duration = max_duration
        self.max_workers = max_workers

        # active thread counter
        self.active_threads = 0
        self.active_lock = threading.Lock()
        self.start_time = None

        # DB writer queue + thread
        self.db_file = db_file
        self.db_queue = Queue()
        self.db_writer_thread = None

        # init db
        self.init_db()

    # ------------------- SQLite -------------------
    def init_db(self):
        # tạo bảng (chạy 1 lần)
        with sqlite3.connect(self.db_file) as conn:
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
        print(f"(DB) Đã khởi tạo DB {self.db_file}")

    def db_writer(self, batch_size=20):
        """
        DB writer thread: đọc từ self.db_queue, gom batch rồi insert.
        Kết thúc khi nhận sentinel None.
        Gọi task_done() cho từng item để db_queue.join() hoạt động đúng.
        """
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()

        print("(DB Writer) Bắt đầu chạy...")
        batch = []

        while True:
            row = self.db_queue.get()  # blocking

            if row is None:
                self.db_queue.task_done()

                if batch:
                    try:
                        cursor.executemany(
                            "INSERT OR IGNORE INTO pages (title, href, content) VALUES (?, ?, ?)",
                            batch
                        )
                        conn.commit()
                        print(f"(DB Writer) Ghi batch cuối {len(batch)} dòng")
                    except Exception as e:
                        print(f"(DB Writer Error) {e}")
                    batch.clear()
                print("(DB Writer) Nhận tín hiệu dừng. Kết thúc.")
                break

            try:
                batch.append((row["title"], row["href"], row["content"]))
            except Exception as e:
                print(f"(DB Writer) Row format error: {e}")

            self.db_queue.task_done()

            if len(batch) >= batch_size:
                try:
                    cursor.executemany(
                        "INSERT OR IGNORE INTO pages (title, href, content) VALUES (?, ?, ?)",
                        batch
                    )
                    conn.commit()
                    print(f"(DB Writer) Ghi batch {len(batch)} dòng")
                except Exception as e:
                    print(f"(DB Writer Error) {e}")
                batch.clear()

        conn.close()
        print("(DB Writer) Đã đóng kết nối DB.")

    def enqueue_db(self, row):
        self.db_queue.put(row)

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

    # ------------------- Normalize URL (loại fragment, trailing slash) -------------------
    def normalize_url(self, url):
        parsed = urlparse(url)
        normalized = parsed._replace(fragment="").geturl()
        if normalized.endswith("/"):
            normalized = normalized[:-1]
        return normalized

    # ------------------- Xử lý URL (driver được truyền vào để tái sử dụng) -------------------
    def process_url(self, url, driver):
        print(f"[Thread-{threading.current_thread().name}] Crawling: {url}")
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
                full_url = self.normalize_url(full_url)
                netloc = urlparse(full_url).netloc
                if self.is_ou_domain(netloc):
                    with self.visited_lock:
                        if full_url not in self.visited:
                            new_urls.append(full_url)
            return result, new_urls

        except Exception as e:
            print(f"(Error) {url}: {e}")
            return None, []
        # driver.quit() sẽ được gọi ở worker cuối cùng (ở finally của worker)

    # ------------------- Worker -------------------
    def worker(self):
        """
        Worker cố gắng tạo driver (có retry), nếu không tạo được thì thoát worker.
        Driver được tạo trước khi tăng active_threads.
        """
        # Try creating driver with retries to avoid single create failure killing run
        driver = None
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                driver = create_driver()
                break
            except Exception as e:
                print(f"(Driver create attempt {attempt}) Error: {e}")
                time.sleep(1)
        if driver is None:
            print("(Worker) Không thể tạo driver, worker sẽ dừng.")
            return

        with self.active_lock:
            self.active_threads += 1

        try:
            while True:
                # dừng theo limit hoặc thời gian
                if self.limit and len(self.results) >= self.limit:
                    break
                if self.max_duration and (time.time() - self.start_time) >= self.max_duration:
                    break

                try:
                    url = self.to_visit.get(timeout=5)
                except Empty:
                    # nếu queue rỗng và chỉ còn 1 active thread -> thoát
                    with self.active_lock:
                        if self.active_threads <= 1:
                            break
                    continue

                # normalise trước khi check visited
                url = self.normalize_url(url)

                with self.visited_lock:
                    if url in self.visited:
                        self.to_visit.task_done()
                        continue
                    self.visited.add(url)

                try:
                    result, new_urls = self.process_url(url, driver)
                except Exception as e:
                    print(f"(Process error) {e}")
                    result, new_urls = None, []

                if result:
                    # đẩy vào DB writer queue (không ghi trực tiếp)
                    self.enqueue_db(result)
                    # lưu vào in-memory results an toàn
                    with self.result_lock:
                        self.results.append(result)

                # thêm new_urls vào queue (nếu chưa visited)
                for new_url in new_urls:
                    with self.visited_lock:
                        if new_url not in self.visited:
                            self.to_visit.put(new_url)

                self.to_visit.task_done()

                # Debug progress (in ra)
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
            # đóng driver khi worker kết thúc
            try:
                driver.quit()
            except Exception:
                pass
            with self.active_lock:
                self.active_threads -= 1

    # ------------------- Run -------------------
    def run(self):
        # start time
        self.start_time = time.time()
        print(f"(Start) to_visit={self.to_visit.qsize()} | visited={len(self.visited)}")

        # start DB writer thread (1 lần)
        if not self.db_writer_thread:
            self.db_writer_thread = threading.Thread(target=self.db_writer, daemon=True)
            self.db_writer_thread.start()

        # start workers
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [executor.submit(self.worker) for _ in range(self.max_workers)]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    print(f"(Worker error) {e}")

        # CHỨNG NĂNG MỚI: chờ DB queue được xử lý sạch trước khi gửi sentinel
        print("(Run) Đợi DB queue được xử lý xong...")
        self.db_queue.join()   # đợi writer gọi task_done() cho mọi item

        print("(Run) Gửi tín hiệu dừng cho DB writer...")
        self.db_queue.put(None)

        # chờ db writer kết thúc
        if self.db_writer_thread:
            self.db_writer_thread.join()

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
        max_workers=3   # mặc định 3, tăng nếu máy đủ mạnh
    )
    try:
        crawler.load_state()
        crawler.run_loop()
    except KeyboardInterrupt:
        print("Dừng bằng tay (Ctrl+C).")
