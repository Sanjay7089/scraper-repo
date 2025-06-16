
import time
import json
import logging
from selenium import webdriver
from tempfile import mkdtemp
from selenium.webdriver.common.by import By

# Setup logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event=None, context=None):
    start_time = time.time()
    driver = None
    try:
        # Setup Chrome driver with Lambda-compatible options
        options = webdriver.ChromeOptions()
        service = webdriver.ChromeService("/opt/chromedriver")

        options.binary_location = '/opt/chrome/chrome'
        options.add_argument("--headless=new")
        options.add_argument('--no-sandbox')
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1280x1696")
        options.add_argument("--single-process")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-dev-tools")
        options.add_argument("--no-zygote")
        options.add_argument(f"--user-data-dir={mkdtemp()}")
        options.add_argument(f"--data-path={mkdtemp()}")
        options.add_argument(f"--disk-cache-dir={mkdtemp()}")
        options.add_argument("--remote-debugging-port=9222")

        driver = webdriver.Chrome(service=service, options=options)

        # Get URL
        url = event.get("url", "https://mycash.utah.gov/app/faq-general")
        logger.info(f"🌐 Navigating to: {url}")
        driver.get(url)
        time.sleep(3)

        # Extract FAQs
        logger.info("🔍 Extracting FAQ data...")
        faq_data = []
        question_elements = driver.find_elements(By.CSS_SELECTOR, "h6.card-title") or driver.find_elements(By.TAG_NAME, "h6")

        for i, q_elem in enumerate(question_elements, 1):
            try:
                question_text = q_elem.text.strip()
                if not question_text or len(question_text) < 5:
                    continue

                # Attempt to find the answer
                try:
                    answer_elem = q_elem.find_element(By.XPATH, "./following-sibling::p[1]")
                    answer_text = answer_elem.text.strip()
                except:
                    try:
                        parent = q_elem.find_element(By.XPATH, "./..")
                        paragraphs = parent.find_elements(By.TAG_NAME, "p")
                        answer_text = next((p.text.strip() for p in paragraphs if len(p.text.strip()) > len(question_text)), "Answer not found")
                    except:
                        answer_text = "Answer not found"

                faq_data.append({
                    "id": f"faq-{i}",
                    "question": question_text,
                    "answer": answer_text,
                    "order": i
                })
            except Exception as e:
                logger.warning(f"⚠️ Error parsing question {i}: {e}")
                continue

        execution_time = round(time.time() - start_time, 2)
        logger.info(f"✅ Extracted {len(faq_data)} FAQs in {execution_time} seconds")

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps({
                "success": True,
                "count": len(faq_data),
                "data": faq_data,
                "execution_time": execution_time,
                "url": url
            })
        }

    except Exception as e:
        logger.error(f"❌ Lambda error: {str(e)}")
        execution_time = round(time.time() - start_time, 2)
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps({
                "success": False,
                "error": str(e),
                "execution_time": execution_time
            })
        }

    finally:
        if driver:
            driver.quit()
            logger.info("🧹 Chrome driver closed")
