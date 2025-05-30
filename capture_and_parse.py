import os
import json
import time
import random
import re
import requests
from datetime import datetime
from itertools import product
from urllib.parse import urlparse
import trafilatura
import browserforge

CONFIG_FILE = 'config.json'
CAPTURES_DIR = 'captures'
USER_AGENT = 'Mozilla/5.0 (compatible; CaptureBot/1.0; +https://github.com/your-repo)'
DELAY_RANGE = (2, 5)  # seconds
MAX_RETRIES = 3
BACKOFF_FACTOR = 2


def load_config():
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)

def get_today(fmt):
    return datetime.utcnow().strftime(fmt)

def substitute(template, variables):
    # Replace ${var} in template with variables[var]
    def replacer(match):
        var = match.group(1)
        return str(variables.get(var, match.group(0)))
    return re.sub(r'\$\{([^}]+)\}', replacer, template)

def expand_targets(defs, targets):
    today = get_today(defs.get('today_format', '%Y-%m-%d'))
    base_vars = {'today': today, **defs}
    base_vars['base'] = substitute(defs.get('base', ''), base_vars)
    expanded = []
    for target in targets:
        # Merge base_vars with target-level vars
        target_vars = target.get('vars', {})
        # If any value in target_vars is a list, expand cartesian product
        keys, values = zip(*[(k, v) for k, v in target_vars.items() if isinstance(v, list)]) if target_vars else ([], [])
        if keys:
            for combo in product(*values):
                combo_vars = dict(zip(keys, combo))
                all_vars = {**base_vars, **target_vars, **combo_vars}
                folder_name = substitute(target.get('folder_name', ''), all_vars)
                url = substitute(target.get('url', ''), all_vars)
                expanded.append({'folder_name': folder_name, 'url': url})
        else:
            all_vars = {**base_vars, **target_vars}
            folder_name = substitute(target.get('folder_name', ''), all_vars)
            url = substitute(target.get('url', ''), all_vars)
            expanded.append({'folder_name': folder_name, 'url': url})
    return expanded


def fetch_url(url):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            fingerprint = browserforge.generate_fingerprint()
            headers = fingerprint.headers
            print(f"Using fingerprint headers: {headers}")
            resp = requests.get(url, headers=headers, timeout=20)
            if resp.status_code == 200:
                return resp.text
            elif resp.status_code in (429, 500, 502, 503, 504):
                time.sleep(BACKOFF_FACTOR ** attempt)
            else:
                print(f"Non-retryable error {resp.status_code} for {url}")
                return None
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            time.sleep(BACKOFF_FACTOR ** attempt)
    print(f"Failed to fetch {url} after {MAX_RETRIES} attempts.")
    return None

def save_content(folder, filename, content):
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, filename), 'w', encoding='utf-8') as f:
        f.write(content)

def save_json(folder, filename, data):
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, filename), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def parse_content(html, url):
    try:
        result = trafilatura.extract(html, output_format='json', url=url)
        if result:
            return json.loads(result)
        else:
            return {'error': 'No main content extracted'}
    except Exception as e:
        return {'error': str(e)}

def generate_folders(defs, targets):
    expanded = expand_targets(defs, targets)
    for entry in expanded:
        folder = os.path.join(CAPTURES_DIR, entry['folder_name'])
        os.makedirs(folder, exist_ok=True)

def send_telegram_message(message):
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        print("Telegram bot token or chat ID not set; skipping notification.")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    try:
        resp = requests.post(url, data=data, timeout=10)
        if resp.status_code != 200:
            print(f"Failed to send Telegram message: {resp.text}")
    except Exception as e:
        print(f"Exception sending Telegram message: {e}")

def main():
    config = load_config()
    defs = config.get('defs', {})
    targets = config.get('target', [])
    generate_folders(defs, targets)
    expanded = expand_targets(defs, targets)
    failures = []
    for entry in expanded:
        folder = os.path.join(CAPTURES_DIR, entry['folder_name'])
        url = entry['url']
        content_path = os.path.join(folder, 'content.html')
        if os.path.exists(content_path) and os.path.getsize(content_path) > 0:
            print(f"Skipping {url} -> {folder} (content.html exists and is non-empty)")
            continue
        print(f"Processing {url} -> {folder}")
        html = fetch_url(url)
        if html:
            save_content(folder, 'content.html', html)
            parsed = parse_content(html, url)
            if 'error' in parsed:
                failures.append({"url": url, "folder": folder, "error": f"parse error: {parsed['error']}"})
            save_json(folder, 'parsed.json', parsed)
        else:
            print(f"Failed to fetch {url}")
            failures.append({"url": url, "folder": folder, "error": "fetch failed"})
        delay = random.uniform(*DELAY_RANGE)
        print(f"Sleeping for {delay:.2f} seconds...")
        time.sleep(delay)
    if failures:
        msg_lines = [f"*Capture Failures* ({datetime.utcnow().isoformat()} UTC):"]
        for f in failures:
            msg_lines.append(f"- `{f['url']}` in `{f['folder']}`: {f['error']}")
        send_telegram_message('\n'.join(msg_lines))

if __name__ == '__main__':
    main()
