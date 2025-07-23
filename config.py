from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options


# Cấu hình ChromeDriver
PATH = r"D:\NCKH\chromedriver.exe"
service = Service(executable_path=PATH)

options = Options()
options.add_argument("--headless")
options.add_argument("--disable-gpu")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-extensions")
options.add_argument("--log-level=3")  # Giảm log rác
prefs = {"profile.managed_default_content_settings.images": 2}  # Tắt tải ảnh
options.add_experimental_option("prefs", prefs)

driver = webdriver.Chrome(service=service, options=options)
driver.set_page_load_timeout(60)