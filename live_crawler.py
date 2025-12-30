import os
import time
import pickle
import threading
import sqlite3
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, urljoin
from queue import PriorityQueue, Empty
from typing import Optional, List, Tuple

from config import create_driver
from extract_content import extract_flexible_content
from bs4 import BeautifulSoup


class LiveCrawler:

    def __init__(
            self,
            start_url: str,
            db_file: str = "crawled_data.db",
            state_file: str = "crawler_state.pkl",
            limit: Optional[int] = None,
            max_duration: Optional[int] = None,
            max_workers: int = 5,
            min_content_length: int = 100
    ):
        self.start_url = start_url
        self.start_netloc = urlparse(start_url).netloc

        # Queue để quản lý URL cần crawl
        self.to_visit = PriorityQueue()
        self.url_counter = 0
        self.to_visit.put((0, self.url_counter, start_url, 0))

        # Set các URL đã crawl
        self.visited = set()
        self.visited_lock = threading.Lock()

        # Cấu hình
        self.limit = limit
        self.max_duration = max_duration
        self.max_workers = max_workers
        self.min_content_length = min_content_length

        # Thread management
        self.active_threads = 0
        self.active_lock = threading.Lock()
        self.start_time = None

        # Database & State
        self.db_file = db_file
        self.state_file = state_file
        self.db_lock = threading.Lock()
        self.init_db()

        # Thống kê
        self.stats = {
            "total_crawled": 0,
            "new_pages": 0,
            "skipped_pages": 0,
            "errors": 0
        }
        self.stats_lock = threading.Lock()

    def init_db(self):
        """Khởi tạo database"""
        conn = sqlite3.connect(self.db_file, check_same_thread=False)
        cursor = conn.cursor()

        # Bảng pages - chỉ lưu: url, title, content, crawled_at
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE NOT NULL,
                title TEXT,
                content TEXT,
                crawled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Index
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_pages_url ON pages(url)")

        conn.commit()
        conn.close()
        print(f"Database initialized: {self.db_file}")

    def save_state(self):
        """Lưu trạng thái crawler để có thể resume"""
        with self.visited_lock, self.stats_lock:
            state = {
                "visited": self.visited,
                "to_visit": list(self.to_visit.queue),
                "url_counter": self.url_counter,
                "stats": self.stats,
                "timestamp": datetime.now().isoformat()
            }

        try:
            with open(self.state_file, "wb") as f:
                pickle.dump(state, f)
            print(f"State saved to {self.state_file}")
        except Exception as e:
            print(f"Error saving state: {e}")

    def load_state(self):
        """Khôi phục trạng thái crawler"""
        if not os.path.exists(self.state_file):
            print(f"No state file found. Starting fresh.")
            return False

        try:
            with open(self.state_file, "rb") as f:
                state = pickle.load(f)

            with self.visited_lock, self.stats_lock:
                self.visited = state.get("visited", set())
                self.url_counter = state.get("url_counter", 0)
                self.stats = state.get("stats", self.stats)

                # Khôi phục queue
                self.to_visit = PriorityQueue()
                for item in state.get("to_visit", []):
                    self.to_visit.put(item)

            timestamp = state.get("timestamp", "unknown")
            print(f"State loaded from {self.state_file}")
            print(f"Last saved: {timestamp}")
            print(f"Visited URLs: {len(self.visited)}")
            print(f"Queue size: {self.to_visit.qsize()}")
            print(f"Previous stats: {self.stats}")
            return True

        except Exception as e:
            print(f"Error loading state: {e}")
            print(f"Starting fresh...")
            return False

    def calc_priority(self, url: str, depth: int) -> int:
        """Tính priority cho URL (số nhỏ = ưu tiên cao)"""
        if url == self.start_url:
            return 0

        url_lower = url.lower()
        # Ưu tiên các trang quan trọng
        high_priority = ['/tuyen-sinh', '/dao-tao', '/tin-tuc', '/thong-bao']
        for keyword in high_priority:
            if keyword in url_lower:
                return 5 + depth

        return 10 + depth

    def is_same_domain(self, netloc: str) -> bool:
        """Check xem URL có cùng domain không"""
        return netloc == self.start_netloc or netloc.endswith(f".{self.start_netloc}")

    def save_page(self, url: str, title: str, content: str):

        # Filter nội dung quá ngắn
        if len(content) < self.min_content_length:
            print(f"FILTERED (too short): {title[:60]}")
            return

        with self.db_lock:
            conn = sqlite3.connect(self.db_file, check_same_thread=False)
            cursor = conn.cursor()

            try:
                # Check xem URL đã tồn tại chưa
                cursor.execute("SELECT 1 FROM pages WHERE url = ? LIMIT 1", (url,))
                existing = cursor.fetchone()

                if existing:
                    # URL đã tồn tại - bỏ qua
                    with self.stats_lock:
                        self.stats["skipped_pages"] += 1
                    print(f"SKIPPED (already exists): {title[:60]}")
                    conn.close()
                    return

                # Insert page mới
                word_count = len(content.split())
                cursor.execute("""
                    INSERT INTO pages (url, title, content)
                    VALUES (?, ?, ?)
                """, (url, title, content))

                conn.commit()

                with self.stats_lock:
                    self.stats["new_pages"] += 1

                print(f"NEW ({word_count} words): {title[:60]}")

            except sqlite3.IntegrityError:
                # URL đã tồn tại (race condition)
                conn.rollback()
                with self.stats_lock:
                    self.stats["skipped_pages"] += 1
                print(f"SKIPPED (duplicate): {title[:60]}")
            except Exception as e:
                conn.rollback()
                print(f"DB Error: {e}")
                with self.stats_lock:
                    self.stats["errors"] += 1
            finally:
                conn.close()

    def process_url(self, url: str, depth: int) -> List[Tuple[int, int, str, int]]:
        """Xử lý một URL"""
        print(f"[{threading.current_thread().name}] Depth={depth} | {url[:80]}")

        driver = create_driver()
        new_urls = []

        try:
            driver.get(url)
            time.sleep(1)  # Đợi page load

            current_url = driver.current_url
            html = driver.page_source

            # Extract content
            title, content, model = extract_flexible_content(html, current_url)

            if title and content:
                # Lưu page (chỉ url, title, content)
                self.save_page(current_url, title, content)

                # Parse để lấy links
                soup = BeautifulSoup(html, "html.parser")

                for tag in soup.find_all("a", href=True):
                    link_url = urljoin(current_url, tag["href"])
                    link_url = link_url.split('#')[0].rstrip('/')

                    if link_url and link_url.startswith('http'):
                        # Thêm vào queue nếu cùng domain
                        if any(x in link_url.lower() for x in ['.pdf', '.doc', '.zip', '.jpg', '.png']):
                            continue

                        netloc = urlparse(link_url).netloc
                        if self.is_same_domain(netloc):
                            with self.visited_lock:
                                if link_url not in self.visited:
                                    priority = self.calc_priority(link_url, depth + 1)
                                    self.url_counter += 1
                                    new_urls.append((priority, self.url_counter, link_url, depth + 1))

                with self.stats_lock:
                    self.stats["total_crawled"] += 1

        except Exception as e:
            print(f"✗ Error crawling {url}: {e}")
            with self.stats_lock:
                self.stats["errors"] += 1
        finally:
            driver.quit()

        return new_urls

    def worker(self):
        """Worker thread"""
        with self.active_lock:
            self.active_threads += 1

        try:
            while True:
                # Check limits
                if self.limit and self.stats["total_crawled"] >= self.limit:
                    break
                if self.max_duration and (time.time() - self.start_time) >= self.max_duration:
                    break

                # Lấy URL từ queue
                try:
                    priority, counter, url, depth = self.to_visit.get(timeout=5)
                except Empty:
                    with self.active_lock:
                        if self.active_threads <= 1:
                            break
                    continue

                # Check đã visit chưa
                with self.visited_lock:
                    if url in self.visited:
                        self.to_visit.task_done()
                        continue
                    self.visited.add(url)

                # Crawl URL
                new_urls = self.process_url(url, depth)

                # Thêm URLs mới vào queue
                for item in new_urls:
                    with self.visited_lock:
                        if item[2] not in self.visited:
                            self.to_visit.put(item)

                self.to_visit.task_done()

                # In thống kê và lưu state định kỳ
                if self.stats["total_crawled"] % 10 == 0:
                    with self.stats_lock:
                        print(f"\n{'=' * 80}")
                        print(f"Progress: {self.stats['total_crawled']} pages crawled")
                        print(f"New: {self.stats['new_pages']} | Skipped: {self.stats['skipped_pages']}")
                        print(f"Queue size: {self.to_visit.qsize()}")
                        print(f"{'=' * 80}\n")

                    # Auto-save state mỗi 10 pages
                    self.save_state()

        finally:
            with self.active_lock:
                self.active_threads -= 1

    def run(self):
        """Chạy crawler"""
        self.start_time = time.time()

        print(f"\n{'=' * 80}")
        print(f"Starting crawler for: {self.start_url}")
        print(f"Workers: {self.max_workers}")
        print(f"Database: {self.db_file}")
        print(f"State file: {self.state_file}")
        print(f"{'=' * 80}\n")

        # Chạy workers
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [executor.submit(self.worker) for _ in range(self.max_workers)]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    print(f"Worker error: {e}")

        duration = time.time() - self.start_time

        # Lưu state cuối cùng
        self.save_state()

        # Kết quả
        print(f"\n{'=' * 80}")
        print(f"COMPLETED in {duration:.2f} seconds")
        print(f"{'=' * 80}")
        print(f"Total crawled:    {self.stats['total_crawled']}")
        print(f"New pages:        {self.stats['new_pages']}")
        print(f"Skipped pages:    {self.stats['skipped_pages']}")
        print(f"Errors:           {self.stats['errors']}")
        print(f"{'=' * 80}\n")


def export_data(db_file: str, output_file: str = "crawled_data.jsonl"):
    """Export dữ liệu ra file JSON Lines"""
    import json

    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT url, title, content, crawled_at
        FROM pages
        ORDER BY crawled_at DESC
    """)

    count = 0
    with open(output_file, 'w', encoding='utf-8') as f:
        for row in cursor.fetchall():
            doc = {
                "url": row[0],
                "title": row[1],
                "content": row[2],
                "crawled_at": row[3]
            }
            f.write(json.dumps(doc, ensure_ascii=False) + '\n')
            count += 1

    conn.close()
    print(f"Exported {count} pages to {output_file}")


def get_stats(db_file: str):
    """Thống kê database"""
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM pages")
    total = cursor.fetchone()[0]

    cursor.execute("SELECT AVG(LENGTH(content)) FROM pages")
    avg_length = cursor.fetchone()[0] or 0

    conn.close()

    print(f"\nDATABASE STATISTICS")
    print(f"{'=' * 60}")
    print(f"Total pages:           {total:,}")
    print(f"Average content length: {avg_length:.0f} chars")
    print(f"{'=' * 60}\n")


# Main
if __name__ == "__main__":
    crawler = LiveCrawler(
        start_url="https://ou.edu.vn",
        db_file="crawled_data.db",
        state_file="crawler_state.pkl",
        max_workers=3,
        limit=None,  # Không giới hạn số trang
        max_duration=None,  # Không giới hạn thời gian
        min_content_length=50
    )

    try:
        # Thử load state cũ
        loaded = crawler.load_state()
        if loaded:
            print("\nResuming from previous session...\n")
        else:
            print("\nStarting new session...\n")

        # Chạy crawler
        crawler.run()

    except KeyboardInterrupt:
        print("\n\nStopped by user - Saving state...")
        crawler.save_state()
        print("State saved. You can resume later by running the script again.")

    finally:
        print("\nGetting statistics...")
        get_stats(crawler.db_file)

        print("\nExporting data...")
        export_data(crawler.db_file, "crawled_data.jsonl")