import os
import json
import time
import random
import re
import requests
from datetime import datetime, timezone
from itertools import product
from urllib.parse import urlparse

import argparse

try:
    import dotenv
    if not os.environ.get('GITHUB_ACTIONS', '').lower() == 'true':
        dotenv.load_dotenv('.env')
except ImportError:
    pass

CONFIG_FILE = 'config.json'
CAPTURES_DIR = 'captures'
DELAY_RANGE = (1, 3)  # seconds, shorter to keep jobs fast
MAX_RETRIES = 3
BACKOFF_FACTOR = 2
REQUEST_TIMEOUT = 10  # seconds

def is_safe_path(base_dir, path):
    base_dir = os.path.abspath(base_dir)
    path = os.path.abspath(path)
    return os.path.commonpath([base_dir]) == os.path.commonpath([base_dir, path])

def load_config():
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)

def substitute(template, variables):
    variables = dict(variables)
    variables['today'] = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    def replacer(match):
        var = match.group(1)
        return str(variables.get(var, match.group(0)))
    return re.sub(r'\$\{([^}]+)\}', replacer, template)

def expand_targets(defs, targets):
    base_vars = {**defs}
    base_vars['base'] = substitute(defs.get('base', ''), base_vars)
    expanded = []
    for target in targets:
        target_vars = target.get('vars', {})
        keys, values = zip(*[(k, v) for k, v in target_vars.items() if isinstance(v, list)]) if target_vars else ([], [])
        if keys:
            for combo in product(*values):
                combo_vars = dict(zip(keys, combo))
                all_vars = {**base_vars, **target_vars, **combo_vars}
                filepath = substitute(target.get('filepath', ''), all_vars)
                url = substitute(target.get('url', ''), all_vars)
                expanded.append({'filepath': filepath, 'url': url})
        else:
            all_vars = {**base_vars, **target_vars}
            filepath = substitute(target.get('filepath', ''), all_vars)
            url = substitute(target.get('url', ''), all_vars)
            expanded.append({'filepath': filepath, 'url': url})
    return expanded

ALLOWED_DOMAINS = {"mshibanami.github.io"}

def fetch_url(url):
    parsed = urlparse(url)
    if parsed.netloc not in ALLOWED_DOMAINS:
        print(f"[ERROR] Refusing to fetch from unauthorized domain: {parsed.netloc}")
        return None
    headers = {"User-Agent": "dev-archive-bot/1.0"}
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                return resp.text
            elif resp.status_code in (429, 500, 502, 503, 504):
                print(f"[WARN] Retrying {url} due to status {resp.status_code} (attempt {attempt}/{MAX_RETRIES})")
                time.sleep(BACKOFF_FACTOR ** attempt)
            else:
                print(f"[ERROR] Non-retryable error {resp.status_code} for {url}")
                return None
        except requests.exceptions.RequestException as e_req:
            print(f"[ERROR] RequestException during fetch for {url} (attempt {attempt}/{MAX_RETRIES}): {e_req}")
            time.sleep(BACKOFF_FACTOR ** attempt)
    print(f"[ERROR] Failed to fetch {url} after {MAX_RETRIES} attempts.")
    return None

def save_content(folder, filename, content):
    os.makedirs(folder, exist_ok=True)
    file_path = os.path.join(folder, filename)
    if not is_safe_path(CAPTURES_DIR, file_path):
        raise ValueError(f"Unsafe path detected: {file_path}")
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

def generate_folders(defs, targets):
    expanded = expand_targets(defs, targets)
    for entry in expanded:
        if 'filepath' not in entry:
            print(f"[ERROR] Entry missing 'filepath': {entry}")
            continue
        filepath = os.path.join(CAPTURES_DIR, entry['filepath'])
        print(f"[INFO] Creating parent directory for: {filepath}")
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

def send_telegram_message(message):
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        print("Telegram bot token or chat ID not set; skipping notification.")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    try:
        resp = requests.post(url, data=data, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            print(f"Failed to send Telegram message: {resp.text}")
    except Exception as e:
        print(f"Exception sending Telegram message: {e}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='Print expanded URLs and paths, then exit')
    parser.add_argument('--test', action='store_true', help='Test mode: process only a subset of items')
    parser.add_argument('--random', action='store_true', help='Shuffle items before processing (only active if --test is also specified)')
    parser.add_argument('--number', type=int, default=1, help='Number of items to process in test mode (default: 1)')
    args = parser.parse_args()

    config = load_config()
    defs = config.get('defs', {})
    targets = config.get('target', [])

    # Initial folder generation for all potential targets might be too much if test mode is very small.
    # Consider moving it after the list is potentially subsetted by --test,
    # or make generate_folders operate on the *actually processed* list.
    # For now, keeping it here as it was.
    generate_folders(defs, targets)
    expanded = expand_targets(defs, targets)

    if args.test:
        if args.random:
            print("[INFO] Test mode: Randomizing target list.")
            random.shuffle(expanded)
        else:
            print("[INFO] Test mode: Using first N targets.")
        if args.number > len(expanded):
            print(f"[WARN] Requested number ({args.number}) is more than available targets ({len(expanded)}). Processing all available.")
            args.number = len(expanded)
        expanded = expanded[:args.number]
        print(f"[INFO] Test mode: Processing {len(expanded)} item(s).")

    if args.dry_run:
        print('[INFO] Dry run: expanded URLs and paths to be processed:')
        if not expanded:
            print("[INFO] No items selected for dry run.")
        for entry in expanded:
            if 'filepath' not in entry:
                print(f"[ERROR] Dry run: Entry missing 'filepath': {entry}")
                continue
            filepath = os.path.join(CAPTURES_DIR, entry['filepath'])
            url = entry.get('url', '[NO URL]')
            print(f"{url} -> {filepath}")
        return

    failures = []
    if not expanded:
        print("[INFO] No items to process.")

    for entry in expanded:
        if 'filepath' not in entry:
            print(f"[ERROR] Main loop: Entry missing 'filepath': {entry}")
            # Potentially add to failures list or send Telegram notification for config error
            continue
        filepath = os.path.join(CAPTURES_DIR, entry['filepath'])
        if not is_safe_path(CAPTURES_DIR, filepath):
            print(f"[ERROR] Unsafe filepath detected: {filepath}")
            failures.append({"url": entry.get('url', '[NO URL]'), "filepath": filepath, "error": "unsafe filepath"})
            continue
        url = entry.get('url', '[NO URL]')
        if url == '[NO URL]':
            print(f"[ERROR] Main loop: Entry missing 'url' for filepath: {filepath}")
            failures.append({"url": "[MISSING URL]", "filepath": filepath, "error": "Missing URL in config entry"})
            continue

        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            print(f"[INFO] Skipping {url} -> {filepath} (file exists and is non-empty)")
            continue

        print(f"[INFO] Processing {url} -> {filepath}")
        content = fetch_url(url)
        if content:
            save_content(os.path.dirname(filepath), os.path.basename(filepath), content)
            print(f"[INFO] Saved content for {url} to {filepath}")
        else:
            print(f"[ERROR] Failed to fetch content for {url}")
            failures.append({"url": url, "filepath": filepath, "error": "fetch failed"})

        delay = random.uniform(*DELAY_RANGE)
        print(f"[INFO] Sleeping for {delay:.2f} seconds...")
        time.sleep(delay)

    if failures:
        msg_lines = [f"*Capture Failures* ({datetime.now(timezone.utc).isoformat()} UTC):"]
        for f in failures:
            msg_lines.append(f"- `{f['url']}` for `{f['filepath']}`: {f['error']}")
        send_telegram_message('\n'.join(msg_lines))

    print("[INFO] Script finished.")

if __name__ == '__main__':
    main()
