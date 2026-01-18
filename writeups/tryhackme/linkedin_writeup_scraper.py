#!/usr/bin/env python3
"""
LinkedIn WriteUp Scraper and Markdown Converter

This script scrapes LinkedIn article/writeup pages and converts them to Markdown format
while preserving the original structure (headings, code blocks, bold, lists, etc.)
and downloading all images in order of appearance.

Usage: python linkedin_writeup_scraper.py <linkedin_article_url>
"""

import os
import sys
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from pathlib import Path


# ANSI color codes for terminal output
class Colors:
    """Terminal color codes for formatted output"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    RESET = '\033[0m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'


def print_success(message):
    """
    Print success message in green with [+] prefix
    
    Args:
        message (str): Success message to display
    """
    print(f"{Colors.GREEN}[+]{Colors.RESET} {message}")


def print_error(message):
    """
    Print error message in red with [-] prefix
    
    Args:
        message (str): Error message to display
    """
    print(f"{Colors.RED}[-]{Colors.RESET} {message}")


def print_info(message):
    """
    Print informational message in blue with [*] prefix
    
    Args:
        message (str): Info message to display
    """
    print(f"{Colors.BLUE}[*]{Colors.RESET} {message}")


def extract_writeup_name_from_title(page_title):
    """
    Extract the writeup name from LinkedIn article title and convert to snake_case.
    
    Handles various formats:
    - "Guide/WriteUp [FR] : TryHackMe - Nom du writeup"
    - "WriteUp/Guide [FR] - TryHackMe : Nom du writeup"
    - "Guide [FR] : TryHackMe - Nom du writeup"
    
    Extracts: "Nom du writeup" -> "nom_du_writeup"
    
    Args:
        page_title (str): The full title from the LinkedIn page
        
    Returns:
        str: Writeup name in snake_case lowercase format (room name only)
    """
    # Remove common prefixes and find the part after "TryHackMe" or "tryhackme"
    # Case insensitive search
    lower_title = page_title.lower()
    
    # Find "tryhackme" in the title
    if 'tryhackme' in lower_title:
        # Find the position of 'tryhackme'
        tryhackme_index = lower_title.index('tryhackme')
        # Get everything after 'tryhackme'
        after_tryhackme = page_title[tryhackme_index + len('tryhackme'):].strip()
        
        # Remove common separators at the beginning (: - or both)
        after_tryhackme = after_tryhackme.lstrip(':- ')
        
        writeup_name = after_tryhackme.strip()
    elif 'hackthebox' in lower_title or 'htb' in lower_title:
        # Handle HackTheBox writeups
        platform_keyword = 'hackthebox' if 'hackthebox' in lower_title else 'htb'
        platform_index = lower_title.index(platform_keyword)
        after_platform = page_title[platform_index + len(platform_keyword):].strip()
        after_platform = after_platform.lstrip(':- ')
        writeup_name = after_platform.strip()
    else:
        # Fallback: try to get the last part after a separator
        if '-' in page_title:
            writeup_name = page_title.split('-')[-1].strip()
        elif ':' in page_title:
            writeup_name = page_title.split(':')[-1].strip()
        else:
            writeup_name = page_title.strip()
    
    # Convert to lowercase and replace spaces with underscores
    writeup_name_snake_case = writeup_name.lower().replace(' ', '_')
    
    # Remove special characters, keep only alphanumeric and underscores
    writeup_name_snake_case = re.sub(r'[^a-z0-9_]', '', writeup_name_snake_case)
    
    return writeup_name_snake_case


def fetch_page_content(url):
    """
    Fetch the HTML content of a LinkedIn article page.
    
    Args:
        url (str): The URL of the LinkedIn article
        
    Returns:
        BeautifulSoup: Parsed HTML content
        
    Raises:
        Exception: If page cannot be fetched
    """
    print_info(f"Fetching page content from: {url}")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        print_success("Page content fetched successfully")
        return BeautifulSoup(response.content, 'html.parser')
    except requests.RequestException as error:
        print_error(f"Failed to fetch page: {error}")
        raise


def remove_unwanted_sections(article_content):
    """
    Remove unwanted sections from the article content (e.g., "report this article", navigation, etc.)
    Be careful not to remove article images or important content.
    
    Args:
        article_content: BeautifulSoup element containing the article
    """
    # List of text patterns that indicate unwanted sections
    unwanted_text_patterns = [
        'report this article',
        'report article',
        'signaler cet article',
        'report this post',
        'published nov',
        'published dec',
        'published jan',
        'published feb',
        'published mar',
        'published apr',
        'published may',
        'published jun',
        'published jul',
        'published aug',
        'published sep',
        'published oct',
        '+ follow'
    ]
    
    # Find and remove elements containing these patterns (case-insensitive)
    for pattern in unwanted_text_patterns:
        # Find all elements that contain this text
        elements_to_remove = article_content.find_all(
            text=lambda text: text and pattern.lower() in text.lower()
        )
        
        for element in elements_to_remove:
            # Remove the parent element to get rid of the whole section
            parent = element.parent
            if parent:
                # Make sure we're not removing important content
                # Check if parent contains images - if so, don't remove it
                if not parent.find('img'):
                    parent.decompose()
    
    # Remove author cards and metadata sections by class
    # These appear before the main content and are redundant since we add author info at the top
    unwanted_selectors = [
        '.publisher-author-card',
        '.base-main-card',
        '[class*="author-card"]',
        '[class*="social-share"]',
        'nav[role="navigation"]',
        'footer',
        '.ellipsis-menu',
        '[data-test-id="publishing-author-card"]'
    ]
    
    for selector in unwanted_selectors:
        unwanted_elements = article_content.select(selector)
        for element in unwanted_elements:
            # For author cards, remove unconditionally (they have profile images, not content images)
            if 'author' in selector.lower() or 'publisher' in selector.lower() or 'base-main-card' in selector:
                element.decompose()
            # For others, double check it doesn't contain content images before removing
            elif not element.find('img', class_=lambda c: c and 'cover-img' not in (c if isinstance(c, str) else ' '.join(c))):
                element.decompose()


def extract_article_content(soup):
    """
    Extract the main article content from LinkedIn page, ignoring sidebar and navigation.
    Also extracts the H1 title and cover image from the header.
    
    Args:
        soup (BeautifulSoup): Parsed HTML of the page
        
    Returns:
        tuple: (article_content, h1_title, cover_image_url) - Article content, H1 title, and cover image URL
    """
    print_info("Extracting article content...")
    
    # First, extract the H1 title from the header
    h1_element = soup.find('h1', class_='pulse-title')
    h1_title = h1_element.get_text().strip() if h1_element else None
    
    if h1_title:
        print_success(f"H1 title found: {h1_title}")
    
    # Extract cover image (appears before the header in LinkedIn structure)
    cover_image_element = soup.find('img', class_='cover-img__image')
    cover_image_url = None
    if cover_image_element:
        cover_image_url = (
            cover_image_element.get('src', '') or 
            cover_image_element.get('data-delayed-url', '') or 
            cover_image_element.get('data-src', '')
        )
        if cover_image_url:
            print_success("Cover image found")
    
    # LinkedIn articles are typically in specific containers
    # Try multiple selectors to find the main content
    possible_selectors = [
        '[data-test-id="article-content-blocks"]',
        'article',
        '.article-content',
        '[class*="article"]',
        'main',
        '.reader-article-content'
    ]
    
    article_content = None
    for selector in possible_selectors:
        article_content = soup.select_one(selector)
        if article_content:
            print_success(f"Article content found using selector: {selector}")
            break
    
    if not article_content:
        # Fallback: use body if specific article container not found
        article_content = soup.find('body')
        print_info("Using body as fallback for article content")
    
    # Debug: count images before filtering
    all_images_before = article_content.find_all('img')
    print_info(f"Found {len(all_images_before)} total images in article content before filtering")
    
    # Remove unwanted sections before processing
    remove_unwanted_sections(article_content)
    print_info("Unwanted sections removed")
    
    # Debug: count images after filtering
    all_images_after = article_content.find_all('img')
    print_info(f"Found {len(all_images_after)} images remaining after filtering")
    
    # Debug: show image URLs
    for idx, img in enumerate(all_images_after):
        img_src = img.get('src', '') or img.get('data-delayed-url', '') or 'NO SRC'
        print_info(f"  Image {idx}: {img_src[:100]}...")
    
    return article_content, h1_title, cover_image_url


def download_image(image_url, output_path, image_name):
    """
    Download an image from URL and save it to the specified path.
    
    Args:
        image_url (str): URL of the image to download
        output_path (str): Full path where the image should be saved
        image_name (str): Name of the image for logging purposes
        
    Returns:
        bool: True if download successful, False otherwise
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(image_url, headers=headers, timeout=30, stream=True)
        response.raise_for_status()
        
        # Write image to file
        with open(output_path, 'wb') as image_file:
            for chunk in response.iter_content(chunk_size=8192):
                image_file.write(chunk)
        
        print_success(f"Image {image_name} downloaded")
        return True
        
    except requests.RequestException as error:
        print_error(f"Problem with image {image_name}: {error}")
        return False


def convert_element_to_markdown(element, writeup_name, image_counter, images_info, depth=0):
    """
    Convert a single HTML element to Markdown format.
    This function processes elements sequentially to maintain proper order, especially for images.
    
    Args:
        element: BeautifulSoup element to convert
        writeup_name (str): Name of the writeup (for image naming)
        image_counter (dict): Counter for image numbering (passed by reference)
        images_info (list): List to store image information (url, filename)
        depth (int): Current nesting depth (for debugging)
        
    Returns:
        str: Markdown formatted text for this element
    """
    if element is None:
        return ""
    
    # Handle text nodes (strings)
    if isinstance(element, str):
        # Return text as-is, will be formatted by parent element
        return element.strip() if element.strip() else ""
    
    # Get the tag name
    tag_name = element.name
    
    # Handle images - they need to be processed immediately to maintain order
    if tag_name == 'img':
        # LinkedIn uses different attributes for images:
        # - 'src' for cover image
        # - 'data-delayed-url' for lazy-loaded inline images
        # - 'data-src' as fallback
        image_url = (
            element.get('src', '') or 
            element.get('data-delayed-url', '') or 
            element.get('data-src', '')
        )
        
        if image_url:
            image_filename = f"{writeup_name}-{image_counter['count']}.png"
            images_info.append({
                'url': image_url,
                'filename': image_filename
            })
            print_info(f"Processing image {image_counter['count']}: {image_url[:80]}...")
            result = f'\n![{image_filename}](images/{image_filename})\n\n'
            image_counter['count'] += 1
            return result
        else:
            print_info(f"Image tag found but no src/data-delayed-url/data-src attribute")
        return ""
    
    # Handle headings
    if tag_name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
        level = int(tag_name[1])
        heading_text = element.get_text().strip()
        
        # H1 is the main title: make it centered and bold
        if level == 1:
            return f'\n<div align="center">\n\n# **{heading_text}**\n\n</div>\n\n'
        else:
            # Other headings: just make them bold
            return '\n' + '#' * level + ' **' + heading_text + '**\n\n'
    
    # Handle paragraphs
    if tag_name == 'p':
        # Check if this paragraph contains a list (LinkedIn sometimes nests lists in paragraphs)
        nested_list = element.find(['ul', 'ol'], recursive=False)
        if nested_list:
            # Process the list directly
            list_type = nested_list.name
            return '\n' + process_list_element(nested_list, list_type, writeup_name, image_counter, images_info) + '\n'
        else:
            # Regular paragraph
            paragraph_content = process_inline_content(element, writeup_name, image_counter, images_info)
            if paragraph_content.strip():
                return paragraph_content + '\n\n'
        return ""
    
    # Handle code blocks
    if tag_name == 'pre':
        # Check if it contains a <code> element
        code_element = element.find('code')
        if code_element:
            code_content = code_element.get_text()
        else:
            code_content = element.get_text()
        return '\n```\n' + code_content.strip() + '\n```\n\n'
    
    # Handle lists
    if tag_name in ['ul', 'ol']:
        list_content = process_list_element(element, tag_name, writeup_name, image_counter, images_info)
        return '\n' + list_content + '\n'
    
    # Handle blockquotes
    if tag_name == 'blockquote':
        quote_text = element.get_text().strip()
        lines = quote_text.split('\n')
        quoted_lines = ['> ' + line for line in lines]
        return '\n' + '\n'.join(quoted_lines) + '\n\n'
    
    # Handle horizontal rules
    if tag_name == 'hr':
        return '\n---\n\n'
    
    # Handle line breaks
    if tag_name == 'br':
        return '\n'
    
    # Handle divs and other container elements - process children sequentially
    if tag_name in ['div', 'section', 'article', 'main', 'body']:
        result = ""
        for child in element.children:
            result += convert_element_to_markdown(child, writeup_name, image_counter, images_info, depth + 1)
        return result
    
    # For other inline elements, process their content
    return process_inline_content(element, writeup_name, image_counter, images_info)


def is_question_text(text):
    """
    Detect if a text is likely a question (ends with ?)
    
    Args:
        text (str): Text to check
        
    Returns:
        bool: True if it looks like a question
    """
    if not text:
        return False
    
    text = text.strip()
    # Check if it ends with a question mark
    return text.endswith('?')


def process_inline_content(element, writeup_name, image_counter, images_info):
    """
    Process inline elements (bold, italic, links, images, etc.) within a paragraph or other container.
    This function handles formatting while maintaining sequential order for images.
    
    Args:
        element: BeautifulSoup element containing inline content
        writeup_name (str): Name of the writeup
        image_counter (dict): Counter for image numbering
        images_info (list): List to store image information
        
    Returns:
        str: Markdown formatted inline text
    """
    result = ""
    
    for child in element.children:
        if isinstance(child, str):
            # Plain text node
            result += child
        elif child.name == 'strong' or child.name == 'b':
            # Bold text
            result += '**' + child.get_text() + '**'
        elif child.name == 'em' or child.name == 'i':
            # Italic text (not a question if not in a list)
            result += '*' + child.get_text() + '*'
        elif child.name == 'span' and 'italic' in child.get('class', []):
            # LinkedIn uses <span class="italic"> for italic text
            # Regular italic text (questions are handled in list processing)
            result += '*' + child.get_text() + '*'
        elif child.name == 'u':
            # Underlined text
            result += '<u>' + child.get_text() + '</u>'
        elif child.name == 'code':
            # Inline code
            result += '`' + child.get_text() + '`'
        elif child.name == 'a':
            # Links
            link_text = child.get_text()
            link_url = child.get('href', '')
            result += f'[{link_text}]({link_url})'
        elif child.name == 'img':
            # Images embedded in inline content
            # LinkedIn uses data-delayed-url for lazy-loaded images
            image_url = (
                child.get('src', '') or 
                child.get('data-delayed-url', '') or 
                child.get('data-src', '')
            )
            
            if image_url:
                image_filename = f"{writeup_name}-{image_counter['count']}.png"
                images_info.append({
                    'url': image_url,
                    'filename': image_filename
                })
                result += f'![{image_filename}](images/{image_filename})'
                image_counter['count'] += 1
        elif child.name == 'br':
            # Line break
            result += '\n'
        else:
            # Recursively process nested elements
            result += process_inline_content(child, writeup_name, image_counter, images_info)
    
    return result


def process_list_element(list_element, list_type, writeup_name, image_counter, images_info):
    """
    Process ordered or unordered lists and convert to Markdown.
    Handles images within list items properly.
    Detects questions (italic text in lists ending with ?) and formats them specially.
    
    Args:
        list_element: BeautifulSoup ul or ol element
        list_type (str): 'ul' for unordered, 'ol' for ordered
        writeup_name (str): Name of the writeup
        image_counter (dict): Counter for image numbering
        images_info (list): List to store image information
        
    Returns:
        str: Markdown formatted list
    """
    markdown_list = ""
    list_items = list_element.find_all('li', recursive=False)
    
    for index, item in enumerate(list_items, 1):
        # Check if this list item contains a question
        # Questions are italic text (em/i or span.italic) ending with ?
        italic_elements = item.find_all(['em', 'i']) + item.find_all('span', class_='italic')
        
        is_question = False
        question_text = ""
        
        for italic_elem in italic_elements:
            text = italic_elem.get_text().strip()
            if is_question_text(text):
                is_question = True
                question_text = text
                break
        
        if is_question:
            # Format as a question with special styling
            markdown_list += f'- 🔍 **Q:** *{question_text}*\n'
        else:
            # Regular list item
            if list_type == 'ul':
                prefix = '- '
            else:  # ordered list
                prefix = f'{index}. '
            
            item_text = process_inline_content(item, writeup_name, image_counter, images_info)
            markdown_list += prefix + item_text.strip() + '\n'
    
    return markdown_list


def extract_author_info(soup):
    """
    Extract author name and profile URL from LinkedIn page metadata.
    
    Args:
        soup (BeautifulSoup): Parsed HTML of the page
        
    Returns:
        tuple: (author_name, profile_url) or (None, None) if not found
    """
    # Method 1: Try to extract from JSON-LD structured data (most reliable)
    json_ld_script = soup.find('script', type='application/ld+json')
    if json_ld_script:
        try:
            import json
            data = json.loads(json_ld_script.string)
            if 'author' in data and isinstance(data['author'], dict):
                author_name = data['author'].get('name', '')
                author_url = data['author'].get('url', '')
                if author_name and author_url:
                    print_success(f"Author found: {author_name}")
                    return author_name, author_url
        except (json.JSONDecodeError, KeyError) as e:
            print_info(f"Could not parse JSON-LD metadata: {e}")
    
    # Method 2: Try to find author card link
    author_card_link = soup.find('a', {'data-tracking-control-name': 'article-ssr-frontend-pulse_publisher-author-card'})
    if author_card_link:
        author_url = author_card_link.get('href', '')
        # Try to find author name in the same section
        author_name_element = author_card_link.find('span', class_='sr-only')
        if not author_name_element:
            # Try h3 with author name
            author_card = author_card_link.parent
            if author_card:
                h3_element = author_card.find('h3')
                if h3_element:
                    author_name = h3_element.get_text().strip()
                else:
                    author_name = "Author"
        else:
            author_name = author_name_element.get_text().strip()
        
        if author_url:
            print_success(f"Author found: {author_name}")
            return author_name, author_url
    
    print_info("Author information not found")
    return None, None


def extract_page_title(soup):
    """
    Extract the page title from LinkedIn article.
    
    Args:
        soup (BeautifulSoup): Parsed HTML of the page
        
    Returns:
        str: Page title
    """
    # Try to find the title in various possible locations
    title_element = soup.find('title')
    if title_element:
        return title_element.get_text().strip()
    
    # Fallback: look for h1
    h1_element = soup.find('h1')
    if h1_element:
        return h1_element.get_text().strip()
    
    return "untitled_writeup"


def create_output_structure(writeup_name):
    """
    Create the output directory structure for the writeup.
    
    Creates:
        - writeup_name/ (main folder)
        - writeup_name/images/ (subfolder for images)
    
    Args:
        writeup_name (str): Name of the writeup in snake_case
        
    Returns:
        tuple: (main_folder_path, images_folder_path)
    """
    print_info(f"Creating output structure for: {writeup_name}")
    
    # Get current working directory
    current_directory = Path.cwd()
    
    # Create main writeup folder
    main_folder = current_directory / writeup_name
    main_folder.mkdir(exist_ok=True)
    
    # Create images subfolder
    images_folder = main_folder / "images"
    images_folder.mkdir(exist_ok=True)
    
    print_success(f"Output structure created at: {main_folder}")
    
    return main_folder, images_folder


def save_markdown_file(markdown_content, output_path, writeup_name):
    """
    Save the generated Markdown content to a file.
    
    Args:
        markdown_content (str): The Markdown formatted text
        output_path (Path): Path to the output folder
        writeup_name (str): Name of the writeup (for filename)
        
    Returns:
        bool: True if saved successfully
    """
    markdown_filepath = output_path / f"{writeup_name}.md"
    
    try:
        with open(markdown_filepath, 'w', encoding='utf-8') as markdown_file:
            markdown_file.write(markdown_content)
        
        print_success(f"Markdown fully generated: {markdown_filepath}")
        return True
        
    except IOError as error:
        print_error(f"Failed to save Markdown file: {error}")
        return False


def main():
    """
    Main function to orchestrate the scraping and conversion process.
    """
    # Check if URL argument is provided
    if len(sys.argv) != 2:
        print_error("Usage: python linkedin_writeup_scraper.py <linkedin_article_url>")
        sys.exit(1)
    
    linkedin_url = sys.argv[1]
    
    print_info("Starting LinkedIn WriteUp Scraper")
    print_info(f"Target URL: {linkedin_url}")
    
    try:
        # Step 1: Fetch the page
        page_soup = fetch_page_content(linkedin_url)
        
        # Step 2: Extract page title and generate writeup name
        page_title = extract_page_title(page_soup)
        print_info(f"Page title: {page_title}")
        
        writeup_name = extract_writeup_name_from_title(page_title)
        print_info(f"Writeup name: {writeup_name}")
        
        # Step 2.5: Extract author information
        author_name, author_url = extract_author_info(page_soup)
        
        # Step 3: Create output structure
        main_folder, images_folder = create_output_structure(writeup_name)
        
        # Step 4: Extract article content, H1 title, and cover image
        article_content, h1_title, cover_image_url = extract_article_content(page_soup)
        
        # Step 5: Convert to Markdown
        print_info("Converting content to Markdown...")
        image_counter = {'count': 0}  # Using dict to allow modification in nested function
        images_info = []  # List to store image URLs and filenames
        
        # Add cover image as image 0 if it exists
        if cover_image_url:
            cover_image_filename = f"{writeup_name}-0.png"
            images_info.append({
                'url': cover_image_url,
                'filename': cover_image_filename
            })
            image_counter['count'] = 1  # Start content images at 1
            print_info(f"Cover image added as {cover_image_filename}")
        
        # Convert article content to markdown
        markdown_content = convert_element_to_markdown(
            article_content, 
            writeup_name, 
            image_counter, 
            images_info
        )
        
        # Build final markdown with proper structure:
        # 1. Title (centered, bold)
        # 2. Author info
        # 3. Separator
        # 4. Cover image
        # 5. Content
        
        final_markdown = ""
        
        # Add H1 title at the very beginning (centered and bold)
        if h1_title:
            final_markdown += f'<div align="center">\n\n# **{h1_title}**\n\n</div>\n\n'
        
        # Add author info after the title if available
        if author_name and author_url:
            final_markdown += f"**Author:** [{author_name}]({author_url})\n\n---\n\n"
        
        # Add cover image after author info
        if cover_image_url:
            cover_image_filename = f"{writeup_name}-0.png"
            final_markdown += f'![{cover_image_filename}](images/{cover_image_filename})\n\n'
        
        # Add the main content
        final_markdown += markdown_content
        
        # Replace the original markdown_content with our structured version
        markdown_content = final_markdown
        
        # Step 6: Save Markdown file
        save_markdown_file(markdown_content, main_folder, writeup_name)
        
        # Step 7: Download images
        print_info(f"Downloading {len(images_info)} images...")
        for image_info in images_info:
            image_url = image_info['url']
            image_filename = image_info['filename']
            image_output_path = images_folder / image_filename
            
            # Make URL absolute if it's relative
            if not image_url.startswith('http'):
                image_url = urljoin(linkedin_url, image_url)
            
            download_image(image_url, image_output_path, image_filename)
        
        print_success(f"Scraping completed! Output saved to: {main_folder}")
        
    except Exception as error:
        print_error(f"Scraping failed: {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
