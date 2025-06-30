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
                    '--single-process',
                    '--no-zygote'
                ]
            )
            logger.info("✅ Browser launched successfully")
            return browser
        except PlaywrightError as e:
            logger.error(f"❌ Failed to launch browser on attempt {attempt + 1}: {str(e)}")
            if attempt < retries:
                time.sleep(1)
            else:
                raise Exception(f"Failed to launch browser after {retries + 1} attempts: {str(e)}")

def extract_faqs_from_page(page):
    """
    Extract FAQ questions and answers from a single page.
    Based on the HTML structure analysis, questions are in h6.card-title
    and answers are in p.card-text elements that follow.
    
    Args:
        page: Playwright page object
    
    Returns:
        List of dictionaries containing question-answer pairs
    """
    faq_data = []
    
    try:
        # Wait for the main content to load
        page.wait_for_selector('section#page-content', timeout=30000)
        
        # Find the card-body container that holds the FAQs
        card_body = page.locator('div.card-body').first
        
        if not card_body.count():
            logger.warning("No card-body container found")
            return faq_data
        
        # Get all h6 question elements within the card-body
        question_elements = card_body.locator('h6.card-title').all()
        
        logger.info(f"Found {len(question_elements)} questions on the page")
        
        for i, question_elem in enumerate(question_elements):
            try:
                question_text = question_elem.inner_text().strip()
                logger.debug(f"Processing question {i+1}: {question_text}")
                
                # Find the answer by looking for p.card-text elements that follow this question
                # We'll collect all p.card-text elements until we hit the next h6.card-title or end
                answer_parts = []
                
                # Get all following siblings within the same card-body
                following_elements = question_elem.locator('xpath=following-sibling::*').all()
                
                for elem in following_elements:
                    tag_name = elem.evaluate('el => el.tagName.toLowerCase()')
                    class_attr = elem.get_attribute('class') or ''
                    
                    # Stop if we hit another question
                    if tag_name == 'h6' and 'card-title' in class_attr:
                        break
                    
                    # Collect answer text from p.card-text elements
                    if tag_name == 'p' and 'card-text' in class_attr:
                        text = elem.inner_text().strip()
                        if text:
                            answer_parts.append(text)
                    
                    # Also collect text from ul/ol lists that might be part of the answer
                    elif tag_name in ['ul', 'ol']:
                        list_items = elem.locator('li').all()
                        for li in list_items:
                            li_text = li.inner_text().strip()
                            if li_text:
                                prefix = "• " if tag_name == 'ul' else f"{len(answer_parts) + 1}. "
                                answer_parts.append(f"{prefix}{li_text}")
                
                # Join answer parts
                if answer_parts:
                    answer_text = "\n\n".join(answer_parts)
                    faq_data.append({
                        "question": question_text,
                        "answer": answer_text
                    })
                    logger.debug(f"✅ Successfully extracted Q&A pair {i+1}")
                else:
                    logger.warning(f"⚠️ No answer found for question: {question_text}")
                    # Still add the question with an empty answer for completeness
                    faq_data.append({
                        "question": question_text,
                        "answer": ""
                    })
            
            except Exception as e:
                logger.error(f"❌ Error processing question {i+1}: {str(e)}")
                continue
    
    except Exception as e:
        logger.error(f"❌ Error extracting FAQs from page: {str(e)}")
    
    return faq_data

def get_faq_urls(page, base_url):
    """
    Extract FAQ category URLs from the navigation tabs.
    
    Args:
        page: Playwright page object
        base_url: Base URL of the website
    
    Returns:
        List of URLs for different FAQ categories
    """
    urls = []
    
    try:
        # Wait for navigation tabs to load
        page.wait_for_selector('ul.nav-tabs', timeout=30000)
        
        # Find all navigation links
        nav_links = page.locator('ul.nav-tabs li.nav-item a.nav-link').all()
        
        for link in nav_links:
            href = link.get_attribute('href')
            if href and href.startswith('/app/faq'):
                full_url = f"{base_url}{href}"
                urls.append(full_url)
                logger.debug(f"Found FAQ URL: {full_url}")
        
        logger.info(f"Extracted {len(urls)} FAQ category URLs")
    
    except Exception as e:
        logger.error(f"Error extracting FAQ URLs: {str(e)}")
    
    return urls

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
        
        with sync_playwright() as p:
            browser = create_browser(p)
            context = browser.new_context()
            
            # If no URLs provided, extract them from the main FAQ page
            if not urls:
                logger.info("🔍 No URLs provided in event. Extracting FAQ category URLs...")
                page = context.new_page()
                
                try:
                    logger.info(f"Navigating to {base_url}/app/faq-general")
                    page.goto(f"{base_url}/app/faq-general", wait_until='networkidle', timeout=30000)
                    urls = get_faq_urls(page, base_url)
                    
                    if not urls:
                        # Fallback to default URLs if extraction fails
                        urls = [
                            f"{base_url}/app/faq-general",
                            f"{base_url}/app/faq-claim",
                            f"{base_url}/app/faq-evidence",
                            f"{base_url}/app/faq-report",
                            f"{base_url}/app/finder-info",
                            f"{base_url}/app/useful-link"
                        ]
                        logger.info(f"Using fallback URLs: {urls}")
                
                finally:
                    page.close()

            # Scrape FAQs from each URL
            grouped_faqs = {}
            
            for url in urls:
                page = context.new_page()
                try:
                    # Extract category ID from URL
                    category_id = url.split('/')[-1].split('#')[0]  # Remove anchor if present
                    category_name = CATEGORY_MAPPING.get(category_id, category_id.replace('-', ' ').title())
                    
                    logger.info(f"🌐 Scraping category '{category_name}' from: {url}")
                    
                    # Navigate to FAQ page
                    page.goto(url, wait_until='networkidle', timeout=30000)
                    
                    # Wait a bit for any dynamic content to load
                    page.wait_for_timeout(3000)
                    
                    # Extract FAQs using the improved method
                    faq_data = extract_faqs_from_page(page)
                    
                    grouped_faqs[category_name] = faq_data
                    all_faq_data.extend(faq_data)
                    
                    logger.info(f"✅ Extracted {len(faq_data)} FAQs from category '{category_name}'")
                
                except (PlaywrightTimeoutError, PlaywrightError) as e:
                    logger.warning(f"⚠️ Failed to load {url}: {str(e)}")
                    category_id = url.split('/')[-1].split('#')[0]
                    category_name = CATEGORY_MAPPING.get(category_id, category_id.replace('-', ' ').title())
                    grouped_faqs[category_name] = []
                
                except Exception as e:
                    logger.error(f"❌ Error scraping {url}: {str(e)}")
                    category_id = url.split('/')[-1].split('#')[0]
                    category_name = CATEGORY_MAPPING.get(category_id, category_id.replace('-', ' ').title())
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