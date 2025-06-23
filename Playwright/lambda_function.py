## FOR SINGLE FAQ PAGE - 

# import time
# import json
# import logging
# from playwright.sync_api import sync_playwright
# from tempfile import mkdtemp
# import os

# # Setup logger
# logger = logging.getLogger()
# logger.setLevel(logging.INFO)

# def lambda_handler(event=None, context=None):
#     start_time = time.time()
#     try:
#         # Initialize Playwright
#         with sync_playwright() as p:
#             # Launch Chromium with Lambda-compatible options
#             logger.info("🌐 Launching headless browser...")
#             user_data_dir = mkdtemp()
#             context = p.chromium.launch_persistent_context(
#                 user_data_dir,
#                 headless=True,
#                 args=[
#                     '--no-sandbox',
#                     '--disable-gpu',
#                     '--single-process',
#                     '--disable-dev-shm-usage',
#                     '--disable-dev-tools',
#                     '--no-zygote',
#                     '--remote-debugging-port=9222',
#                     '--window-size=1280,1696'
#                 ]
#             )
#             page = context.new_page()

#             # Get URL
#             url = event.get("url", "https://mycash.utah.gov/app/faq-general")
#             logger.info(f"🌐 Navigating to: {url}")
#             page.goto(url, wait_until='networkidle')
#             page.wait_for_selector('h6.card-title', timeout=30000)
#             page.wait_for_timeout(3000)

#             # Extract FAQs
#             logger.info("🔍 Extracting FAQ data...")
#             faq_data = []
#             question_elements = page.query_selector_all('.card-body h6.card-title')

#             for i, q_elem in enumerate(question_elements, 1):
#                 try:
#                     question_text = q_elem.inner_text().strip()
#                     if not question_text or len(question_text) < 5:
#                         continue

#                     # Find the answer
#                     try:
#                         answer_elem = q_elem.query_selector('xpath=./following-sibling::p[1][contains(@class, "card-text")]')
#                         answer_text = answer_elem.inner_text().strip() if answer_elem else "Answer not found"
#                     except Exception as e:
#                         logger.warning(f"⚠️ Error finding answer for question {i}: {e}")
#                         answer_text = "Answer not found"

#                     faq_data.append({
#                         "id": f"faq-{i}",
#                         "question": question_text,
#                         "answer": answer_text,
#                         "order": i
#                     })
#                 except Exception as e:
#                     logger.warning(f"⚠️ Error parsing question {i}: {e}")
#                     continue

#             execution_time = round(time.time() - start_time, 2)
#             logger.info(f"✅ Extracted {len(faq_data)} FAQs in {execution_time} seconds")

#             return {
#                 "statusCode": 200,
#                 "headers": {
#                     "Content-Type": "application/json",
#                     "Access-Control-Allow-Origin": "*"
#                 },
#                 "body": json.dumps({
#                     "success": True,
#                     "count": len(faq_data),
#                     "data": faq_data,
#                     "execution_time": execution_time,
#                     "url": url
#                 })
#             }

#     except Exception as e:
#         logger.error(f"❌ Lambda error: {str(e)}")
#         execution_time = round(time.time() - start_time, 2)
#         return {
#             "statusCode": 500,
#             "headers": {
#                 "Content-Type": "application/json",
#                 "Access-Control-Allow-Origin": "*"
#             },
#             "body": json.dumps({
#                 "success": False,
#                 "error": str(e),
#                 "execution_time": execution_time
#             })
#         }

#     finally:
#         logger.info("🧹 Browser resources cleaned up by Playwright")

# # For local testing
# if __name__ == "__main__":
#     result = lambda_handler({}, {})
#     print(json.dumps(result, indent=2))

import json
import logging
import os
import sys
import time
import traceback
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

# Category ID to human-readable name mapping
CATEGORY_MAPPING = {
    "faq-general": "General",
    "faq-claim": "Claiming Property",
    "faq-evidence": "Evidence",
    "faq-report": "Reporting Property",
    "finder-info": "Fee Finder",
    "useful-link": "Useful Links"
}

def create_browser(p, retries=2):
    """
    Attempt to create a browser instance with retries.
    """
    for attempt in range(retries + 1):
        try:
            logger.info(f"🌐 Launching headless browser (attempt {attempt + 1}/{retries + 1})...")
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-dev-tools',
                    '--disable-gpu',
                    '--disable-extensions',
                    '--single-process',  # Reduce resource usage
                    '--no-zygote'  # Optimize for Lambda
                ]
            )
            logger.info("✅ Browser launched successfully")
            return browser
        except PlaywrightError as e:
            logger.error(f"❌ Failed to launch browser on attempt {attempt + 1}: {str(e)}")
            if attempt < retries:
                time.sleep(1)  # Wait before retry
            else:
                raise Exception(f"Failed to launch browser after {retries + 1} attempts: {str(e)}")

def lambda_handler(event=None, context=None):
    """
    AWS Lambda handler function to scrape FAQs from mycash.utah.gov.
    Supports both Lambda execution and local testing.
    """
    start_time = time.time()
    all_faq_data = []
    urls = []
    base_url = "https://mycash.utah.gov"

    try:
        # Use default event for local testing if none provided
        if event is None:
            event = {"urls": []}
            logger.info("Running locally with default event: %s", event)

        # Check if URLs are provided in the event, else scrape them
        urls = event.get("urls", [])
        if not urls:
            logger.info("🔍 No URLs provided in event. Extracting FAQ category URLs...")
            with sync_playwright() as p:
                browser = create_browser(p)
                context = browser.new_context()
                page = context.new_page()
                
                try:
                    # Navigate to FAQ general page
                    logger.info(f"Navigating to {base_url}/app/faq-general")
                    page.goto(f"{base_url}/app/faq-general", wait_until='networkidle', timeout=15000)
                    page.wait_for_selector('ul.nav-tabs', timeout=60000)
                    
                    # Extract navigation links
                    nav_links = page.query_selector_all('ul.nav-tabs li.nav-item a.nav-link')
                    urls = [f"{base_url}{link.get_attribute('href')}" for link in nav_links if link.get_attribute('href')]
                    logger.info(f"📋 Found {len(urls)} FAQ category URLs: {urls}")
                
                finally:
                    context.close()
                    browser.close()

        # Scrape FAQs from each URL
        with sync_playwright() as p:
            browser = create_browser(p)
            context = browser.new_context()
            grouped_faqs = {}

            for url in urls:
                page = context.new_page()
                try:
                    # Extract category ID from URL
                    category_id = url.split('/')[-1]
                    category_name = CATEGORY_MAPPING.get(category_id, category_id.replace('-', ' ').title())
                    logger.info(f"🌐 Navigating to: {url}")
                    
                    # Navigate to FAQ page
                    page.goto(url, wait_until='networkidle', timeout=15000)
                    page.wait_for_selector('h6.card-title', timeout=60000, state='attached')
                    page.wait_for_timeout(10000)  # Wait for dynamic content
                    
                    # Extract FAQs
                    logger.info(f"🔍 Extracting FAQ data from {url}...")
                    faq_data = []
                    question_elements = page.query_selector_all('.card-body h6.card-title')
                    
                    if not question_elements:
                        logger.warning(f"⚠️ No FAQ questions found on {url}")
                        grouped_faqs[category_name] = []
                        continue

                    for i, q_elem in enumerate(question_elements, 1):
                        try:
                            question_text = q_elem.inner_text().strip()
                            answer_text = []
                            
                            # Get all sibling elements until next h6.card-title
                            siblings = q_elem.evaluate_handle(
                                '''el => {
                                    let siblings = [];
                                    let next = el.nextElementSibling;
                                    while (next && !next.matches('h6.card-title')) {
                                        siblings.push(next);
                                        next = next.nextElementSibling;
                                    }
                                    return siblings;
                                }'''
                            ).as_element()

                            # Process each sibling
                            for sibling in siblings or []:
                                tag_name = sibling.evaluate('el => el.tagName').lower()
                                
                                if tag_name == 'p' and 'card-text' in sibling.get_attribute('class', ''):
                                    text = sibling.inner_text().strip()
                                    if text:
                                        answer_text.append(text)
                                
                                elif tag_name in ['ul', 'ol']:
                                    list_type = 'ordered' if tag_name == 'ol' else 'unordered'
                                    items = sibling.query_selector_all('li')
                                    for item in items:
                                        item_text = item.inner_text().strip()
                                        prefix = f"{len(answer_text) + 1}. " if list_type == 'ordered' else "- "
                                        answer_text.append(f"{prefix}{item_text}")
                                        
                                        # Handle nested lists
                                        nested_lists = item.query_selector_all('ul, ol')
                                        for nested in nested_lists:
                                            nested_type = 'ordered' if nested.evaluate('el => el.tagName').lower() == 'ol' else 'unordered'
                                            nested_items = nested.query_selector_all('li')
                                            for nested_item in nested_items:
                                                nested_text = nested_item.inner_text().strip()
                                                nested_prefix = f"  {len(answer_text) + 1}. " if nested_type == 'ordered' else "  - "
                                                answer_text.append(f"{nested_prefix}{nested_text}")
                            
                            # Fallback: Check all p.card-text in card-body
                            if not answer_text:
                                card_body = q_elem.query_selector('xpath=ancestor::div[contains(@class, "card-body")]')
                                if card_body:
                                    all_p = card_body.query_selector_all('p.card-text')
                                    for p in all_p:
                                        text = p.inner_text().strip()
                                        if text:
                                            answer_text.append(text)
                            
                            if answer_text:
                                faq_data.append({
                                    "question": question_text,
                                    "answer": "\n".join(answer_text)
                                })
                                logger.debug(f"Question {i} on {url}: {question_text}\nAnswer: {answer_text}")
                            else:
                                logger.warning(f"⚠️ No answer found for question {i} on {url}: {question_text}")
                        
                        except Exception as e:
                            logger.error(f"❌ Error parsing question {i} on {url}: {str(e)}")
                            continue
                    
                    grouped_faqs[category_name] = faq_data
                    all_faq_data.extend(faq_data)
                    logger.info(f"✅ Extracted {len(faq_data)} FAQs from {url}")
                
                except (PlaywrightTimeoutError, PlaywrightError) as e:
                    logger.warning(f"⚠️ Failed to load {url} or find FAQ elements: {str(e)}")
                    grouped_faqs[category_name] = []
                finally:
                    page.close()
            
            context.close()
            browser.close()
        
        execution_time = time.time() - start_time
        logger.info(f"✅ Total extracted {len(all_faq_data)} FAQs in {execution_time:.2f} seconds")
        
        # Return successful response
        response = {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps({
                "success": True,
                "count": len(all_faq_data),
                "data": grouped_faqs,
                "execution_time": f"{execution_time:.2f} seconds",
                "urls": urls
            })
        }
        
        # For local testing, print the response
        if event == {"urls": []}:
            print(json.dumps(response, indent=2))
        
        return response
    
    except Exception as e:
        logger.error(f"❌ Fatal Lambda error: {str(e)}\n{traceback.format_exc()}")
        execution_time = time.time() - start_time
        
        # Return error response
        response = {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps({
                "success": False,
                "error": str(e),
                "execution_time": f"{execution_time:.2f} seconds",
                "urls": urls
            })
        }
        
        # For local testing, print the error response
        if event == {"urls": []}:
            print(json.dumps(response, indent=2))
        
        return response

if __name__ == "__main__":
    # Support local execution for debugging
    lambda_handler()

#? TODO: add logic for saving response to s3 bucket using boto3 ( use seprate lambda to do so)

