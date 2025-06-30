

Lambda Function: Uses a container image (stored in ECR) with Playwright to scrape FAQs.
EventBridge Scheduler: Triggers the Lambda function weekly (cron(0 8 ? * 6 *), America/New_York).
S3 Bucket: Stores JSON output in faq-output/faq_data_YYYYMMDD_HHMMSS.json.
Bedrock Knowledge Base: Ingests S3 data for querying FAQs.

Files

lambda_function.py: Main Lambda handler, orchestrates scraping, and uploads to S3.
faq_general.py, faq_claim.py, faq_evidence.py, faq_report.py: Extract FAQs (questions in <h6 class="card-title">, answers in <p class="card-text"> or <ul>/<ol> lists).
finder_info.py: Extracts FAQs with potential links (<a> tags) formatted as Markdown.
useful_link.py: Extracts links (<a> tags) as Q&A pairs.
faq-scraper-stack.yaml: CloudFormation template to deploy Lambda, S3, and scheduler.

Extraction Logic
Common Categories (General, Claiming Property, Evidence, Reporting Property)

HTML Structure: Assumes FAQs in <div class="card-body"> within <section id="page-content">. Questions in <h6 class="card-title">, answers in <p class="card-text"> or <ul>/<ol> lists.
Process:
Wait for section#page-content (30s timeout).
Locate div.card-body and extract h6.card-title questions.
For each question, collect following <p.card-text> and list items until the next question.
Format answers with \n\n separators.
Return [{"question": "...", "answer": "..."}, ...].


Error Handling: Returns empty lists for failed pages, logs missing content or timeouts.

Fee Finder

Same as above, but includes <a> tags in answers, formatted as [text](href).

Useful Links

HTML Structure: Assumes <a> tags in card-body.
Process:
Extract all <a> tags.
Use link text as question and [text](href) as answer.
Skip empty/invalid links.



Execution Flow

Scheduler Trigger: EventBridge invokes Lambda every Friday at 8:00 AM ET.
Lambda Initialization: Sets up boto3 S3 client, logging, and FAQScraper.
Scrape Categories:
Generate URLs (https://mycash.utah.gov/app/<category>).
Launch Playwright Chromium browser (headless).
For each category:
Navigate to URL, wait for networkidle and 3s for dynamic content.
Extract FAQs using category-specific function.
Store in grouped_faqs dictionary.




Format Output: Flatten FAQs into [{"category": "...", "question": "...", "answer": "..."}, ...] for Bedrock.
Upload to S3: Save JSON to s3://<bucket>/faq-output/.
Return Response: Include FAQs, count, and S3 location.
Cleanup: Close browser.

Deployment

Build ECR Image:docker build -t faq-scraper .
aws ecr get-login-password | docker login --username AWS --password-stdin ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com
docker push ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/faq-scraper:latest

