import logging
import time
import boto3
import json
import os
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError
from faq_general import extract_faq_general
from faq_claim import extract_faq_claim
from faq_evidence import extract_faq_evidence
from faq_report import extract_faq_report
from finder_info import extract_finder_info
from useful_link import extract_useful_link

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Remove existing handlers to avoid duplication
for handler in logger.handlers[:]:
    logger.removeHandler(handler)

# Create console handler with formatting
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Initialize AWS clients
s3_client = boto3.client('s3')
cloudwatch = boto3.client('cloudwatch')

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
    def __init__(self, base_url):
        self.base_url = base_url
        self.browser = None
        self.context = None
        self.start_time = time.time()
    
    def get_default_faq_urls(self):
        """Get list of FAQ URLs to scrape"""
        return [
            f"{self.base_url}/app/faq-general",
            f"{self.base_url}/app/faq-claim",
            f"{self.base_url}/app/faq-evidence",
            f"{self.base_url}/app/faq-report",
            f"{self.base_url}/app/finder-info",
            f"{self.base_url}/app/useful-link"
        ]
    
    def create_browser(self, p, retries=2):
        """Create browser instance with retry logic"""
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
                        '--no-zygote',
                        '--disable-background-timer-throttling',
                        '--disable-backgrounding-occluded-windows',
                        '--disable-renderer-backgrounding'
                    ]
                )
                logger.info("✅ Browser launched successfully")
                return browser
            except PlaywrightError as e:
                logger.error(f"❌ Failed to launch browser on attempt {attempt + 1}: {str(e)}")
                if attempt < retries:
                    time.sleep(2 ** attempt)  # Exponential backoff
                else:
                    raise Exception(f"Failed to launch browser after {retries + 1} attempts: {str(e)}")
    
    def extract_category_from_url(self, url):
        """Extract category ID and name from URL"""
        category_id = url.split('/')[-1].split('#')[0]
        category_name = CATEGORY_MAPPING.get(category_id, category_id.replace('-', ' ').title())
        return category_id, category_name
    
    def get_extraction_method(self, category_id):
        """Get the appropriate extraction method for a category"""
        method_mapping = {
            "faq-general": extract_faq_general,
            "faq-claim": extract_faq_claim,
            "faq-evidence": extract_faq_evidence,
            "faq-report": extract_faq_report,
            "finder-info": extract_finder_info,
            "useful-link": extract_useful_link
        }
        return method_mapping.get(category_id, extract_faq_general)
    
    def scrape_single_category(self, url, max_retries=2):
        """Scrape a single category with retry logic"""
        category_id, category_name = self.extract_category_from_url(url)
        
        for attempt in range(max_retries + 1):
            page = None
            try:
                logger.info(f"🌐 Scraping category '{category_name}' from: {url} (attempt {attempt + 1})")
                page = self.context.new_page()
                
                # Set longer timeout for initial page load
                page.goto(url, wait_until='networkidle', timeout=60000)
                page.wait_for_timeout(3000)
                
                extraction_method = self.get_extraction_method(category_id)
                faq_data = extraction_method(page)
                
                logger.info(f"✅ Extracted {len(faq_data)} FAQs from category '{category_name}'")
                return category_name, faq_data
                
            except (PlaywrightTimeoutError, PlaywrightError) as e:
                logger.warning(f"⚠️ Failed to load {url} on attempt {attempt + 1}: {str(e)}")
                if attempt < max_retries:
                    time.sleep(2 ** attempt)  # Exponential backoff
                else:
                    logger.error(f"❌ Failed to scrape {url} after {max_retries + 1} attempts")
                    return category_name, []
            except Exception as e:
                logger.error(f"❌ Unexpected error scraping {url}: {str(e)}")
                return category_name, []
            finally:
                if page:
                    try:
                        page.close()
                    except:
                        pass
        
        return category_name, []
    
    def scrape_all_categories(self, urls):
        """Scrape all categories"""
        grouped_faqs = {}
        total_count = 0
        errors = []
        
        with sync_playwright() as p:
            try:
                self.browser = self.create_browser(p)
                self.context = self.browser.new_context(
                    user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                )
                
                for url in urls:
                    try:
                        category_name, faq_data = self.scrape_single_category(url)
                        grouped_faqs[category_name] = faq_data
                        total_count += len(faq_data)
                    except Exception as e:
                        error_msg = f"Failed to process {url}: {str(e)}"
                        logger.error(error_msg)
                        errors.append(error_msg)
                        
            finally:
                try:
                    if self.context:
                        self.context.close()
                    if self.browser:
                        self.browser.close()
                except:
                    pass
        
        return grouped_faqs, total_count, errors

def publish_cloudwatch_metrics(total_count, execution_time, errors_count):
    """Publish custom metrics to CloudWatch"""
    try:
        cloudwatch.put_metric_data(
            Namespace='Lambda/FAQScraper',
            MetricData=[
                {
                    'MetricName': 'FAQsScraped',
                    'Value': total_count,
                    'Unit': 'Count',
                    'Timestamp': datetime.now(timezone.utc)
                },
                {
                    'MetricName': 'ExecutionTime',
                    'Value': execution_time,
                    'Unit': 'Seconds',
                    'Timestamp': datetime.now(timezone.utc)
                },
                {
                    'MetricName': 'ErrorsCount',
                    'Value': errors_count,
                    'Unit': 'Count',
                    'Timestamp': datetime.now(timezone.utc)
                }
            ]
        )
        logger.info("✅ Published CloudWatch metrics")
    except Exception as e:
        logger.error(f"❌ Failed to publish CloudWatch metrics: {str(e)}")

def lambda_handler(event, context):
    """Main Lambda handler"""
    start_time = time.time()
    
    # Get environment variables
    bucket_name = os.environ.get('BUCKET_NAME')
    aws_region = os.environ.get('AWS_REGION', 'us-east-1')
    
    if not bucket_name:
        logger.error("❌ BUCKET_NAME environment variable not set")
        raise ValueError("BUCKET_NAME environment variable is required")
    
    logger.info(f"🚀 Starting FAQ scraping job")
    logger.info(f"📧 Event: {json.dumps(event, default=str)}")
    logger.info(f"🪣 Target S3 bucket: {bucket_name}")
    
    base_url = "https://mycash.utah.gov"
    scraper = FAQScraper(base_url)
    urls = scraper.get_default_faq_urls()
    
    try:
        # Scrape all categories
        grouped_faqs, total_count, errors = scraper.scrape_all_categories(urls)
        
        # Calculate execution time
        execution_time = time.time() - start_time
        
        # Prepare output for S3
        timestamp = datetime.now(timezone.utc)
        output = {
            'metadata': {
                'timestamp': timestamp.isoformat(),
                'total_count': total_count,
                'execution_time_seconds': round(execution_time, 2),
                'source_url': base_url,
                'lambda_request_id': context.aws_request_id,
                'errors': errors,
                'categories_processed': len(grouped_faqs)
            },
            'data': {
                'faqs': grouped_faqs
            }
        }
        
        # Generate S3 key with timestamp
        timestamp_str = timestamp.strftime('%Y%m%d_%H%M%S')
        s3_key = f"faq-output/faq_data_{timestamp_str}.json"
        
        # Write to S3
        try:
            s3_client.put_object(
                Bucket=bucket_name,
                Key=s3_key,
                Body=json.dumps(output, indent=2, default=str),
                ContentType='application/json',
                ServerSideEncryption='AES256',
                Metadata={
                    'total-faqs': str(total_count),
                    'execution-time': str(round(execution_time, 2)),
                    'lambda-request-id': context.aws_request_id
                }
            )
            logger.info(f"✅ Successfully wrote FAQ data to s3://{bucket_name}/{s3_key}")
            
        except Exception as e:
            logger.error(f"❌ Failed to write to S3: {str(e)}")
            raise e
        
        # Publish CloudWatch metrics
        publish_cloudwatch_metrics(total_count, execution_time, len(errors))
        
        # Prepare response
        response = {
            'statusCode': 200,
            'body': {
                'message': 'FAQ scraping completed successfully',
                'total_faqs_scraped': total_count,
                'categories_processed': len(grouped_faqs),
                'execution_time_seconds': round(execution_time, 2),
                's3_location': f"s3://{bucket_name}/{s3_key}",
                'errors_count': len(errors),
                'timestamp': timestamp.isoformat()
            }
        }
        
        if errors:
            response['body']['errors'] = errors
            logger.warning(f"⚠️ Completed with {len(errors)} errors")
        
        logger.info(f"🎉 FAQ scraping completed. Total FAQs: {total_count}, Time: {execution_time:.2f}s")
        return response
        
    except Exception as e:
        execution_time = time.time() - start_time
        error_msg = f"❌ Fatal error in FAQ scraping: {str(e)}"
        logger.error(error_msg)
        
        # Try to publish error metrics
        try:
            publish_cloudwatch_metrics(0, execution_time, 1)
        except:
            pass
        
        # Return error response
        return {
            'statusCode': 500,
            'body': {
                'message': 'FAQ scraping failed',
                'error': str(e),
                'execution_time_seconds': round(execution_time, 2),
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
        }

# For local testing
if __name__ == "__main__":
    # Set up test environment
    os.environ['BUCKET_NAME'] = 'scrapping-test-123'
    os.environ['AWS_REGION'] = 'us-east-1'
    
    # Mock context for local testing
    class MockContext:
        aws_request_id = 'test-request-id'
    
    # Test the scraper
    test_event = {"source": "local-test"}
    result = lambda_handler(test_event, MockContext())
    print(json.dumps(result, indent=2, default=str))