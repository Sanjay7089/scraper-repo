import logging

logger = logging.getLogger()

def extract_useful_link(page):
    """
    Extract information from Useful Links category page.
    Assumes links are primary content, possibly with descriptions.
    
    Args:
        page: Playwright page object
        
    Returns:
        List of FAQ dictionaries (links treated as answers)
    """
    faq_data = []
    
    try:
        # Wait for the main content to load
        page.wait_for_selector('section#page-content', timeout=30000)
        
        # Find the card-body container that holds the content
        card_body = page.locator('div.card-body').first
        
        if not card_body.count():
            logger.warning("No card-body container found")
            return faq_data
        
        # Get all link elements (assuming links are in <a> tags)
        link_elements = card_body.locator('a').all()
        
        logger.info(f"Found {len(link_elements)} links on the page")
        
        for i, link_elem in enumerate(link_elements):
            try:
                link_text = link_elem.inner_text().strip()
                href = link_elem.get_attribute('href') or ''
                
                if not link_text or not href:
                    logger.debug(f"Skipping empty link at index {i+1}")
                    continue
                
                logger.debug(f"Processing link {i+1}: {link_text}")
                
                # Treat link text as question and href as answer
                faq_data.append({
                    "question": link_text,
                    "answer": f"[{link_text}]({href})"
                })
                logger.debug(f"✅ Successfully extracted link {i+1}")
            
            except Exception as e:
                logger.error(f"❌ Error processing link {i+1}: {str(e)}")
                continue
    
    except Exception as e:
        logger.error(f"❌ Error extracting links from page: {str(e)}")
    
    return faq_data