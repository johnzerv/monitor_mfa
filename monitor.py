import os
import requests
import json
import re
import time
import argparse
from bs4 import BeautifulSoup

class Monitor:
    """Generic base class for monitoring a numeric value on a webpage."""
    def __init__(self, url, region, refresh_interval=10):
        self.url = url
        self.refresh_interval = refresh_interval
        self.region = region
        self.prev_value = None
        self.first_run = True
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.google.com/"
        }

    def fetch_html(self):
        try:
            response = requests.get(self.url, headers=self.headers, timeout=20)
            response.raise_for_status()
            return response.text
        except Exception as e:
            self.on_error(f"Fetch Error: {e}")
            return None

    def get_value(self):
        raise NotImplementedError("Subclasses must implement get_value()")

    def on_change(self, value, metadata, is_initial=False):
        """Hook for subclasses to override."""
        pass

    def on_no_change(self, value):
        """Hook for subclasses to override."""
        pass

    def on_error(self, message):
        """Hook for subclasses to override."""
        print(f"Error: {message}")

    def run(self):
        while True:
            result = self.get_value() # Returns (value, metadata)
            
            if result and result[0] is not None and result[0] != -1:
                current_value, metadata = result
                
                if self.first_run:
                    # PASS is_initial=True here
                    self.on_change(current_value, metadata, is_initial=True)
                    self.prev_value = current_value
                    self.first_run = False

                elif current_value != self.prev_value:
                    self.on_change(current_value, metadata, is_initial=False)
                    self.prev_value = current_value
                else:
                    self.on_no_change(current_value)
            else:
                self.on_error("Could not parse data.")

            time.sleep(self.refresh_interval)


class AirbnbMonitor(Monitor):
    def __init__(self, url, region, refresh_interval=10, log_filename="airbnb.log"):
        super().__init__(url, region, refresh_interval)
        self.log_filename = f"logs/{log_filename}"

        if not os.path.exists(self.log_filename):
            self._write_to_file("EVENT | REGION | AVAILABILITY | CHANGE | METADATA")    
    
    def _write_to_file(self, message):
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        with open(self.log_filename, "a+", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")
            f.flush()

    def _find_key_recursive(self, obj, key):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == key: return v
                res = self._find_key_recursive(v, key)
                if res: return res
        elif isinstance(obj, list):
            for item in obj:
                res = self._find_key_recursive(item, key)
                if res: return res
        return None

    def _extract_number(self, title_string):
        if not title_string: return -1
        match = re.search(r'([\d\.,]+)', title_string)
        if match:
            num_str = match.group(1).replace(',', '').replace('.', '')
            return int(num_str)
        return -1

    def get_value(self):
        html = self.fetch_html()
        if not html: return None, None

        soup = BeautifulSoup(html, "html.parser")
        scripts = soup.find_all("script", {"type": "application/json"})
        
        structured_title = None
        for script in scripts:
            if "structuredTitle" in script.text:
                try:
                    data = json.loads(script.text)
                    structured_title = self._find_key_recursive(data, "structuredTitle")
                    break
                except: continue

        if not structured_title:
            match = re.search(r'"structuredTitle"\s*:\s*"([^"]+)"', html)
            if match: structured_title = match.group(1)

        if structured_title:
            return self._extract_number(structured_title), structured_title
        return -1, None
    
    # Override the hooks
    def on_change(self, value, metadata, is_initial=False):
        status = "START" if is_initial else "CHANGE"
        # Calculate diff only if it's not the first run
        diff = 0 if is_initial else (value - self.prev_value)
        diff_str = f"{diff:+}"
        
        log_entry = f"{status} | {self.region} | {value} | {diff_str} | {metadata}"
        
        print(f"[{time.strftime('%H:%M:%S')}] {log_entry}")
        self._write_to_file(log_entry)

    def on_no_change(self, value):
        print(f"[{time.strftime('%H:%M:%S')}] {self.region}: No change ({value})")

    def on_error(self, message):
        err_msg = f"ERROR | {self.region} | {message}"
        print(f"[{time.strftime('%H:%M:%S')}] {err_msg}")
        self._write_to_file(err_msg)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", type=str, required=True)
    parser.add_argument("--region", type=str, default="Athens Center")
    parser.add_argument("--refresh_interval", type=int, default=10)
    parser.add_argument("--output", type=str, default="airbnb.log")
    args = parser.parse_args()

    monitor = AirbnbMonitor(
        url=args.url, 
        region=args.region, 
        refresh_interval=args.refresh_interval, 
        log_filename=args.output
    )
    
    print(f"Monitoring {args.region}... logging to {args.output}")
    try:
        monitor.run()
    except KeyboardInterrupt:
        print("\nStopped.")