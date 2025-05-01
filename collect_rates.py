import os
import random
import pandas as pd
from time import time
from unidecode import unidecode
from typing import List, Dict, Union
from datetime import datetime, timedelta, timezone
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
import knime.scripting.io as knio
import sys

# ─────────────────────────────────────────────────────────────
# Utility to print safely (removes non-ASCII chars like ❌)
# ─────────────────────────────────────────────────────────────
def safe_print(text: str):
    text = ''.join(c for c in text if ord(c) < 128)
    print(text)

# ─────────────────────────────────────────────────────────────
# Utility Functions
# ─────────────────────────────────────────────────────────────
def normalize_string(s: str) -> str:
    return unidecode(s.strip().lower())

def create_webdriver() -> WebDriver:
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.5735.110 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ]
    chosen_user_agent = random.choice(user_agents)

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument(f"user-agent={chosen_user_agent}")

    driver_path = r"C:\Drivers\chrome-win64\chromedriver.exe"
    service = Service(executable_path=driver_path)
    driver = webdriver.Chrome(service=service, options=options)
    return driver

def wait_for_page_load(driver: WebDriver, timeout: int = 10):
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.XPATH, '//div[@data-testid="property-card"]'))
        )
        safe_print("Page loaded successfully.")
    except Exception as e:
        safe_print(f"Page load timeout: {e}")

# ─────────────────────────────────────────────────────────────
# Scraping Function
# ─────────────────────────────────────────────────────────────
def collect_hotel_prices(driver: WebDriver, city: str, checkin_date: str, checkout_date: str, hotel_competitors: List[str]) -> Dict[str, Union[int, float]]:
    safe_print(f"Scraping data for {city} - Check-in: {checkin_date} to {checkout_date}")
    
    search_url = (
        f"https://www.booking.com/searchresults.html?"
        f"ss={city}&checkin={checkin_date}&checkout={checkout_date}"
        f"&group_adults=2&no_rooms=1&group_children=0"
    )
    driver.get(search_url)
    wait_for_page_load(driver)

    # ✅ Brazil local time (UTC-3)
    now = datetime.now(timezone(timedelta(hours=-3)))

    hotel_prices = {
        "Check_in": checkin_date,
        "Timestamp": now.strftime("%Y-%m-%d"),
        "Timestamp_DB": now.isoformat()
    }

    try:
        hotel_elements = driver.find_elements(By.XPATH, '//div[@data-testid="property-card"]')
        for hotel in hotel_elements:
            try:
                name_element = hotel.find_element(By.XPATH, './/div[@data-testid="title"]')
                hotel_name = normalize_string(name_element.text)

                if hotel_name not in hotel_competitors:
                    continue

                price_elements = hotel.find_elements(By.XPATH, './/span[@data-testid="price-and-discounted-price"]')
                prices = [
                    int("".join(filter(str.isdigit, normalize_string(price.text))))
                    for price in price_elements if price.text
                ]

                hotel_prices[hotel_name.title()] = min(prices) if prices else None

            except Exception as e:
                safe_print(f"Error fetching details for {hotel_name}: {str(e)}")
    except Exception as e:
        safe_print(f"Error fetching hotels: {str(e)}")

    return hotel_prices

# ─────────────────────────────────────────────────────────────
# Save and Output Function (Wide Format)
# ─────────────────────────────────────────────────────────────
def save_hotel_price_date(results: List[Dict[str, Union[int, float]]]) -> None:
    df = pd.DataFrame(results)

    cols_to_convert = df.columns.difference(['Check_in', 'Timestamp', 'Timestamp_DB'])
    df[cols_to_convert] = df[cols_to_convert].apply(pd.to_numeric, errors='coerce')
    df = df[['Check_in', 'Timestamp', 'Timestamp_DB'] + sorted(cols_to_convert)]

    os.makedirs("data", exist_ok=True)
    filename = f"data/{df['Check_in'][0]}_booking_hotel_prices.csv"
    df.to_csv(filename, index=False, encoding='utf-8')
    safe_print(f"✅ Data saved to {filename}")

    knio.output_tables[0] = knio.Table.from_pandas(df)

# ─────────────────────────────────────────────────────────────
# Main Execution
# ─────────────────────────────────────────────────────────────
t1 = time()
city = "Taubate"

driver = create_webdriver()

# Adjust number of days here
date_list = [(datetime.today() + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(61)]

hotel_competitors = [
    "Faro Hotel Taubaté", "Carlton Plaza Baobá", "Olavo Bilac Hotel",
    "Ibis Taubate", "Ibis Styles Taubate",
    "Gran Continental Hotel Taubaté", "KEEP SUÍTES HOTEL"
]
hotel_competitors_normalized = [normalize_string(hotel) for hotel in hotel_competitors]

results = [
    collect_hotel_prices(driver, city, date_list[i], date_list[i + 1], hotel_competitors_normalized)
    for i in range(len(date_list) - 1)
]

driver.quit()

save_hotel_price_date(results)
safe_print(f"\n⏱ Time taken: {round(time() - t1, 2)}s")
