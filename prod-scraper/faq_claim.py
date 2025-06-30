import logging

logger = logging.getLogger()

def extract_faq_claim(page):
    """
    Extract FAQs from Claiming Property category page.
    Assumes similar structure to General FAQs (h6.card-title, p.card-text, lists).
    
    Args:
        page: Playwright page object
        
    Returns:
        List of FAQ dictionaries
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
                    
                    # Collect text from ul/ol lists that might be part of the answer
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