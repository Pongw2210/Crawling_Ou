import sqlite3
import pandas as pd

# ==== CẤU HÌNH HIỂN THỊ (QUAN TRỌNG) ====
pd.set_option("display.max_columns", None)      # hiện tất cả cột
pd.set_option("display.width", None)            # không giới hạn chiều ngang
pd.set_option("display.max_colwidth", 300)      # không cắt text dài

# ==== KẾT NỐI DB ====
conn = sqlite3.connect("crawled_data.db")

# ==== ĐỌC BẢNG pages ====
df_pages = pd.read_sql_query(
    "SELECT * FROM pages",
    conn
)

# ==== XEM THÔNG TIN ====
print("=== INFO ===")
df_pages.info()

print("\n=== 5 RECORD ĐẦU ===")
print(df_pages.head())

# ==== ĐÓNG KẾT NỐI ====
conn.close()

