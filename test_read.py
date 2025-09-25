import sqlite3
import pandas as pd

# Kết nối tới DB
conn = sqlite3.connect("ou_output.db")

# Đọc toàn bộ bảng 'pages' vào DataFrame
df = pd.read_sql_query("SELECT * FROM pages", conn)

conn.close()

# Xem thông tin
print(df.info())
print(df.head())
print("CONTENT",df['content'][0])
print("HREF",df['href'][0])
print("TITLE",df['title'][0])