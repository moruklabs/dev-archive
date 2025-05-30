#!/usr/bin/env python3
"""
HTML to YAML Parser
Parses captured HTML files using purehtml and extracts structured data into YAML format.
"""

import os
import json
import yaml
import argparse
import purehtml
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from pathlib import Path
import re

CAPTURES_DIR = 'captures'
PARSED_DIR = 'parsed'

def clean_text(text):
    """Clean and normalize text content."""
    if not text:
        return ""
    return re.sub(r'\s+', ' ', text.strip())

def parse_hackernews_html(html_content, filepath):
    """Parse Hacker News HTML and extract story data."""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    stories = []
    story_rows = soup.find_all('tr', class_='athing')
    
    for row in story_rows:
        story_id = row.get('id', '')
        
        # Get rank
        rank_elem = row.find('span', class_='rank')
        rank = clean_text(rank_elem.text) if rank_elem else ""
        
        # Get title and URL
        titleline = row.find('span', class_='titleline')
        if titleline:
            title_link = titleline.find('a')
            title = clean_text(title_link.text) if title_link else ""
            url = title_link.get('href', '') if title_link else ""
            
            # Get site info
            sitebit = titleline.find('span', class_='sitebit')
            site = ""
            if sitebit:
                site_span = sitebit.find('span', class_='sitestr')
                site = clean_text(site_span.text) if site_span else ""
        else:
            title = ""
            url = ""
            site = ""
        
        # Get metadata from next row (subtext)
        next_row = row.find_next_sibling('tr')
        score = ""
        author = ""
        time_ago = ""
        comments = ""
        
        if next_row:
            subtext = next_row.find('td', class_='subtext')
            if subtext:
                # Score
                score_elem = subtext.find('span', class_='score')
                score = clean_text(score_elem.text) if score_elem else ""
                
                # Author
                author_elem = subtext.find('a', class_='hnuser')
                author = clean_text(author_elem.text) if author_elem else ""
                
                # Time
                age_elem = subtext.find('span', class_='age')
                if age_elem:
                    age_link = age_elem.find('a')
                    time_ago = clean_text(age_link.text) if age_link else ""
                
                # Comments
                comment_links = subtext.find_all('a')
                for link in comment_links:
                    if 'comments' in link.text or 'discuss' in link.text:
                        comments = clean_text(link.text)
                        break
        
        if story_id and title:  # Only add stories with essential data
            stories.append({
                'id': story_id,
                'rank': rank,
                'title': title,
                'url': url,
                'site': site,
                'score': score,
                'author': author,
                'time_ago': time_ago,
                'comments': comments
            })
    
    return {
        'source': 'hackernews',
        'captured_at': extract_date_from_path(filepath),
        'url': 'https://news.ycombinator.com/',
        'stories': stories
    }

def parse_github_trending_html(html_content, filepath):
    """Parse GitHub trending page HTML."""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    repos = []
    repo_articles = soup.find_all('article', class_='Box-row')
    
    for article in repo_articles:
        repo_data = {}
        
        # Repository name and URL
        h2_elem = article.find('h2', class_=['h3', 'lh-condensed'])
        if h2_elem:
            repo_link = h2_elem.find('a')
            if repo_link:
                repo_data['name'] = clean_text(repo_link.text)
                repo_data['url'] = f"https://github.com{repo_link.get('href', '')}"
        
        # Description
        desc_elem = article.find('p', class_='col-9')
        if desc_elem:
            repo_data['description'] = clean_text(desc_elem.text)
        
        # Language
        lang_elem = article.find('span', {'itemprop': 'programmingLanguage'})
        if lang_elem:
            repo_data['language'] = clean_text(lang_elem.text)
        
        # Stars, forks, etc.
        link_elements = article.find_all('a', class_=['Link', 'Link--muted'])
        for link in link_elements:
            href = link.get('href', '')
            text = clean_text(link.text)
            if '/stargazers' in href:
                repo_data['stars'] = text
            elif '/forks' in href:
                repo_data['forks'] = text
        
        # Stars today
        stars_today_elem = article.find('span', class_='d-inline-block')
        if stars_today_elem:
            # Look for star icon + number pattern
            star_span = stars_today_elem.find('span', class_='text-normal')
            if star_span:
                repo_data['stars_today'] = clean_text(star_span.text)
        
        if repo_data.get('name'):  # Only add repos with essential data
            repos.append(repo_data)
    
    # Extract language and interval from filepath
    path_parts = filepath.split('/')
    language = ""
    interval = ""
    
    for i, part in enumerate(path_parts):
        if part == 'trending' and i + 1 < len(path_parts):
            interval = path_parts[i + 1]
            if i + 2 < len(path_parts) and not path_parts[i + 2].endswith('.html'):
                language = path_parts[i + 2].replace('-trending.html', '')
            break
    
    return {
        'source': 'github_trending',
        'language': language or 'overall',
        'interval': interval,
        'captured_at': extract_date_from_path(filepath),
        'url': reconstruct_github_url(language, interval),
        'repositories': repos
    }

def parse_github_topics_html(html_content, filepath):
    """Parse GitHub topics page HTML."""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    repos = []
    repo_articles = soup.find_all('article', class_='Box-row')
    
    for article in repo_articles:
        repo_data = {}
        
        # Repository name and URL
        h3_elem = article.find('h3')
        if h3_elem:
            repo_link = h3_elem.find('a')
            if repo_link:
                repo_data['name'] = clean_text(repo_link.text)
                repo_data['url'] = f"https://github.com{repo_link.get('href', '')}"
        
        # Description
        desc_elem = article.find('p', class_='color-fg-muted')
        if desc_elem:
            repo_data['description'] = clean_text(desc_elem.text)
        
        # Language
        lang_elem = article.find('span', {'itemprop': 'programmingLanguage'})
        if lang_elem:
            repo_data['language'] = clean_text(lang_elem.text)
        
        # Stars and forks
        link_elements = article.find_all('a', class_=['Link', 'Link--muted'])
        for link in link_elements:
            href = link.get('href', '')
            text = clean_text(link.text)
            if '/stargazers' in href:
                repo_data['stars'] = text
            elif '/forks' in href:
                repo_data['forks'] = text
        
        if repo_data.get('name'):  # Only add repos with essential data
            repos.append(repo_data)
    
    # Extract topic from filepath
    topic = ""
    path_parts = filepath.split('/')
    for part in path_parts:
        if part.endswith('.html') and 'topics' in filepath:
            topic = part.replace('.html', '')
            break
    
    return {
        'source': 'github_topics',
        'topic': topic,
        'captured_at': extract_date_from_path(filepath),
        'url': f"https://github.com/topics/{topic}",
        'repositories': repos
    }

def parse_producthunt_html(html_content, filepath):
    """Parse Product Hunt HTML (basic structure extraction)."""
    # Use purehtml to clean the HTML first
    cleaned_html = purehtml.purify_html_str(html_content)
    soup = BeautifulSoup(cleaned_html, 'html.parser')
    
    # Extract basic page information
    title_elem = soup.find('title')
    title = clean_text(title_elem.text) if title_elem else ""
    
    # Look for product listings (this is a simplified approach)
    products = []
    
    # Product Hunt has complex dynamic structure, so we'll extract basic text content
    headings = soup.find_all(['h1', 'h2', 'h3', 'h4'])
    links = soup.find_all('a', href=True)
    
    # Extract some structured data
    product_links = [link for link in links if '/posts/' in link.get('href', '')]
    
    for link in product_links[:10]:  # Limit to first 10
        products.append({
            'title': clean_text(link.text),
            'url': link.get('href', '')
        })
    
    return {
        'source': 'producthunt',
        'captured_at': extract_date_from_path(filepath),
        'url': 'https://www.producthunt.com/',
        'page_title': title,
        'products': products
    }

def extract_date_from_path(filepath):
    """Extract date from capture filepath."""
    # Example: captures/capture/2025-05-30/...
    parts = filepath.split('/')
    for part in parts:
        if re.match(r'\d{4}-\d{2}-\d{2}', part):
            return part
    return datetime.now(timezone.utc).strftime('%Y-%m-%d')

def reconstruct_github_url(language, interval):
    """Reconstruct the original GitHub URL."""
    base_url = "https://github.com/trending"
    if language and language != 'overall':
        return f"{base_url}/{language}?since={interval}"
    return f"{base_url}?since={interval}"

def parse_html_file(filepath):
    """Parse a single HTML file and return structured data."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        # Determine parser based on filepath
        if 'hackernews' in filepath:
            return parse_hackernews_html(html_content, filepath)
        elif 'gh/trending' in filepath:
            return parse_github_trending_html(html_content, filepath)
        elif 'gh/topics' in filepath:
            return parse_github_topics_html(html_content, filepath)
        elif 'ph' in filepath:
            return parse_producthunt_html(html_content, filepath)
        else:
            # Generic parser using purehtml
            cleaned_html = purehtml.purify_html_str(html_content)
            soup = BeautifulSoup(cleaned_html, 'html.parser')
            title = soup.find('title')
            return {
                'source': 'generic',
                'captured_at': extract_date_from_path(filepath),
                'page_title': clean_text(title.text) if title else "",
                'content': cleaned_html[:1000]  # First 1000 chars of cleaned content
            }
    
    except Exception as e:
        print(f"[ERROR] Failed to parse {filepath}: {e}")
        return None

def save_yaml_data(data, output_path):
    """Save structured data as YAML file."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

def find_html_files(base_dir):
    """Find all HTML files in the captures directory."""
    html_files = []
    for root, dirs, files in os.walk(base_dir):
        for file in files:
            if file.endswith('.html'):
                html_files.append(os.path.join(root, file))
    return html_files

def main():
    parser = argparse.ArgumentParser(description='Parse captured HTML files to YAML format')
    parser.add_argument('--input-dir', default=CAPTURES_DIR, help='Input directory containing HTML files')
    parser.add_argument('--output-dir', default=PARSED_DIR, help='Output directory for YAML files')
    parser.add_argument('--test', action='store_true', help='Test mode: process only a few files')
    parser.add_argument('--dry-run', action='store_true', help='Print files to be processed without actually processing them')
    
    args = parser.parse_args()
    
    # Find all HTML files
    html_files = find_html_files(args.input_dir)
    
    if args.test:
        html_files = html_files[:5]  # Process only first 5 files in test mode
        print(f"[INFO] Test mode: Processing {len(html_files)} files")
    
    if args.dry_run:
        print(f"[INFO] Found {len(html_files)} HTML files to process:")
        for html_file in html_files:
            print(f"  {html_file}")
        return
    
    processed_count = 0
    failed_count = 0
    
    for html_file in html_files:
        print(f"[INFO] Processing {html_file}")
        
        # Generate output path
        rel_path = os.path.relpath(html_file, args.input_dir)
        yaml_path = os.path.join(args.output_dir, rel_path.replace('.html', '.yaml'))
        
        # Skip if YAML file already exists and is newer than HTML file
        if os.path.exists(yaml_path) and os.path.getmtime(yaml_path) > os.path.getmtime(html_file):
            print(f"[INFO] Skipping {html_file} (YAML file is up to date)")
            continue
        
        # Parse HTML file
        data = parse_html_file(html_file)
        
        if data:
            # Add metadata
            data['processed_at'] = datetime.now(timezone.utc).isoformat()
            data['source_file'] = rel_path
            
            # Save as YAML
            save_yaml_data(data, yaml_path)
            print(f"[INFO] Saved parsed data to {yaml_path}")
            processed_count += 1
        else:
            print(f"[ERROR] Failed to parse {html_file}")
            failed_count += 1
    
    print(f"[INFO] Processing complete. Processed: {processed_count}, Failed: {failed_count}")

if __name__ == '__main__':
    main()