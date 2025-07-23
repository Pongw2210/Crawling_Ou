import pickle
import time
from urllib.parse import urlparse


def run(start_url, limit=None, max_duration=None):
    start_time = time.time()
    start_netloc = urlparse(start_url).netloc
    to_visit= set([start_url])
    visited = set()
    results = []

    while to_visit:
        if limit and len(results) >= limit:
            print(f"(Run) Dat gioi han {limit} ket qua. Dung crawl.")
            break

        if max_duration and (time.time()-start_time) >= max_duration:
            print(f"(Run) Het thoi gian gioi han {max_duration} giay. Dung va luu trang thai.")
            with open('crawler_state.pkl', 'wb') as f:
                pickle.dump({
                    'visited': visited,
                    'to_visit': to_visit,
                    'results': results
                }, f)
            print("(Save_State) Đã lưu trạng thái crawl vào crawler_state.pkl")

        current_url = to_visit.pop()
        if current_url in visited:
            continue

        visited.add(current_url)
        print(f"[{len(results)} kết quả, {len(to_visit)} chờ] Đang xử lý: {current_url}")


