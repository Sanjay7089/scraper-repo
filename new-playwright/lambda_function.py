import logging
import time
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError
from faq_general import extract_faq_general
from faq_claim import extract_faq_claim
from faq_evidence import extract_faq_evidence
from faq_report import extract_faq_report
from finder_info import extract_finder_info
from useful_link import extract_useful_link
import json

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)  # Set to DEBUG for detailed output
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Category ID to human-readable name mapping
CATEGORY_MAPPING = {
    "faq-general": "General",
    "faq-claim": "Claiming Property",
    "faq-evidence": "Evidence",
    "faq-report": "Reporting Property",
    "finder-info": "Fee Finder",
    "useful-link": "Useful Links"
}

class FAQScraper:
    """
    A utility class to scrape FAQs from mycash.utah.gov
    """
    
    def __init__(self, base_url):
        self.base_url = base_url
        self.browser = None
        self.context = None
    
    def get_default_faq_urls(self):
        """
        Get the default FAQ category URLs.
        
        Returns:
            List of default FAQ URLs
        """
        return [
            f"{self.base_url}/app/faq-general",
            f"{self.base_url}/app/faq-claim",
            f"{self.base_url}/app/faq-evidence",
            f"{self.base_url}/app/faq-report",
            f"{self.base_url}/app/finder-info",
            f"{self.base_url}/app/useful-link"
        ]
    
    def create_browser(self, p, retries=2):
        """
        Attempt to create a browser instance with retries.
        
        Args:
            p: Playwright instance
            retries: Number of retry attempts
            
        Returns:
            Browser instance
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
    
    def extract_category_from_url(self, url):
        """
        Extract category information from URL.
        
        Args:
            url: FAQ category URL
            
        Returns:
            Tuple of (category_id, category_name)
        """
        category_id = url.split('/')[-1].split('#')[0]  # Remove anchor if present
        category_name = CATEGORY_MAPPING.get(category_id, category_id.replace('-', ' ').title())
        return category_id, category_name
    
    def get_extraction_method(self, category_id):
        """
        Get the appropriate extraction method based on category ID.
        
        Args:
            category_id: The category identifier
            
        Returns:
            Extraction method function
        """
        method_mapping = {
            "faq-general": extract_faq_general,
            "faq-claim": extract_faq_claim,
            "faq-evidence": extract_faq_evidence,
            "faq-report": extract_faq_report,
            "finder-info": extract_finder_info,
            "useful-link": extract_useful_link
        }
        
        return method_mapping.get(category_id, extract_faq_general)  # Default to general extraction
    
    def scrape_single_category(self, url):
        """
        Scrape FAQs from a single category URL.
        
        Args:
            url: FAQ category URL
            
        Returns:
            Tuple of (category_name, faq_data_list)
        """
        category_id, category_name = self.extract_category_from_url(url)
        page = self.context.new_page()
        
        try:
            logger.info(f"🌐 Scraping category '{category_name}' from: {url}")
            
            # Navigate to FAQ page
            page.goto(url, wait_until='networkidle', timeout=30000)
            
            # Wait a bit for any dynamic content to load
            page.wait_for_timeout(3000)
            
            # Get the appropriate extraction method for this category
            extraction_method = self.get_extraction_method(category_id)
            
            # Extract FAQs using the category-specific method
            faq_data = extraction_method(page)
            
            logger.info(f"✅ Extracted {len(faq_data)} FAQs from category '{category_name}'")
            return category_name, faq_data
        
        except (PlaywrightTimeoutError, PlaywrightError) as e:
            logger.warning(f"⚠️ Failed to load {url}: {str(e)}")
            return category_name, []
        
        except Exception as e:
            logger.error(f"❌ Error scraping {url}: {str(e)}")
            return category_name, []
        
        finally:
            page.close()
    
    def scrape_all_categories(self, urls):
        """
        Scrape FAQs from all provided URLs.
        
        Args:
            urls: List of FAQ category URLs
            
        Returns:
            Tuple of (grouped_faqs_dict, total_count)
        """
        grouped_faqs = {}
        total_count = 0
        
        with sync_playwright() as p:
            self.browser = self.create_browser(p)
            self.context = self.browser.new_context()
            
            try:
                for url in urls:
                    category_name, faq_data = self.scrape_single_category(url)
                    grouped_faqs[category_name] = faq_data
                    total_count += len(faq_data)
                
            finally:
                self.context.close()
                self.browser.close()
        
        return grouped_faqs, total_count

def lambda_handler(event, context):
    """
    AWS Lambda handler to scrape FAQs.
    
    Args:
        event: Lambda event data
        context: Lambda context data
        
    Returns:
        Dictionary with scraped FAQs
    """
    base_url = "https://mycash.utah.gov"
    scraper = FAQScraper(base_url)
    urls = scraper.get_default_faq_urls()
    
    grouped_faqs, total_count = scraper.scrape_all_categories(urls)
    
    return {
        'statusCode': 200,
        'body': {
            'faqs': grouped_faqs,
            'total_count': total_count
        }
    }

if __name__ == "__main__":
    # For local testing
    base_url = "https://mycash.utah.gov"
    scraper = FAQScraper(base_url)
    urls = scraper.get_default_faq_urls()
    
    grouped_faqs, total_count = scraper.scrape_all_categories(urls)
    
    # Print results in a readable format
    print(json.dumps({
        'faqs': grouped_faqs,
        'total_count': total_count
    }, indent=2))