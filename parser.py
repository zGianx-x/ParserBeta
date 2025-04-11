import tkinter as tk
from tkinter import scrolledtext, ttk, messagebox, filedialog
import threading
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import queue
import os
import re
import time
import random
from urllib.parse import quote_plus

class DorkParser:
    def __init__(self, root):
        self.root = root
        self.root.title("Advanced Dork Parser")
        self.root.geometry("800x700")
        self.root.configure(bg="#f0f0f0")
        
        # Variables
        self.is_running = False
        self.is_paused = False
        self.valid_urls = []
        self.current_dork_index = 0
        self.results_queue = queue.Queue()
        self.active_threads = []
        self.lock = threading.Lock()
        
        # Search engines configuration
        self.search_engines = {
            'Bing': {
                'url': lambda dork, page=0: f"https://www.bing.com/search?q={dork}&first={page*10+1}&count=100",
                'max_pages': 10,
                'parser': self.parse_bing
            },
            'DuckDuckGo': {
                'url': lambda dork, page=0: f"https://html.duckduckgo.com/html/?q={dork}&s={page*30}",
                'max_pages': 5,
                'parser': self.parse_duckduckgo
            },
            'Yahoo': {
                'url': lambda dork, page=0: f"https://search.yahoo.com/search?p={dork}&b={page*10+1}",
                'max_pages': 10,
                'parser': self.parse_yahoo
            },
            'AOL': {
                'url': lambda dork, page=0: f"https://search.aol.com/aol/search?q={dork}&b={page*10+1}",
                'max_pages': 10,
                'parser': self.parse_aol
            },
            'Google APIs': {
                'url': lambda dork, page=0: f"https://www.googleapis.com/customsearch/v1?q={dork}&start={page*10+1}&key=YOUR_API_KEY&cx=YOUR_CX_KEY",
                'max_pages': 10,
                'parser': self.parse_google_api
            },
            'Bing News': {
                'url': lambda dork, page=0: f"https://www.bing.com/news/search?q={dork}&first={page*10+1}",
                'max_pages': 5,
                'parser': self.parse_bing_news
            },
            'Naver': {
                'url': lambda dork, page=0: f"https://search.naver.com/search.naver?query={dork}&start={page*10+1}",
                'max_pages': 5,
                'parser': self.parse_naver
            },
            'Yandex': {
                'url': lambda dork, page=0: f"https://yandex.com/search/?text={dork}&p={page}",
                'max_pages': 10,
                'parser': self.parse_yandex
            }
        }
        
        # Headers with different user agents
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/91.0.864.59'
        ]
        
        # Stats for each engine
        self.engine_stats = {engine: {'total': 0, 'valid': 0} for engine in self.search_engines.keys()}
        
        # Create UI elements
        self.create_ui()
        
        # Update stats periodically
        self.root.after(100, self.update_from_queue)

    def create_ui(self):
        # Create frames
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Top section: Dorks input
        dork_frame = ttk.LabelFrame(main_frame, text="Dorks", padding="10")
        dork_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Text area for dorks
        self.dork_text = scrolledtext.ScrolledText(dork_frame, height=10)
        self.dork_text.pack(fill=tk.BOTH, expand=True)
        
        btn_frame = ttk.Frame(dork_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(btn_frame, text="Load Dorks File", command=self.load_dorks_file).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Clear", command=lambda: self.dork_text.delete(1.0, tk.END)).pack(side=tk.LEFT, padx=5)
        
        # Middle section: Search engines selection
        engine_frame = ttk.LabelFrame(main_frame, text="Search Engines", padding="10")
        engine_frame.pack(fill=tk.X, pady=5)
        
        # Create checkboxes for each engine
        self.engine_vars = {}
        engine_inner_frame = ttk.Frame(engine_frame)
        engine_inner_frame.pack(fill=tk.X)
        
        col, row = 0, 0
        for engine in self.search_engines.keys():
            var = tk.BooleanVar(value=True)
            self.engine_vars[engine] = var
            cb = ttk.Checkbutton(engine_inner_frame, text=engine, variable=var)
            cb.grid(row=row, column=col, sticky="w", padx=10, pady=2)
            col += 1
            if col > 3:  # 4 checkboxes per row
                col = 0
                row += 1
        
        # Thread count slider
        thread_frame = ttk.Frame(main_frame)
        thread_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(thread_frame, text="Threads:").pack(side=tk.LEFT, padx=5)
        self.thread_var = tk.IntVar(value=10)
        thread_scale = ttk.Scale(thread_frame, from_=1, to=50, orient=tk.HORIZONTAL, 
                                variable=self.thread_var, length=200)
        thread_scale.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        thread_label = ttk.Label(thread_frame, textvariable=self.thread_var)
        thread_label.pack(side=tk.LEFT, padx=5)
        
        # Control buttons
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=10)
        
        self.start_button = ttk.Button(control_frame, text="Start Search", command=self.start_search)
        self.start_button.pack(side=tk.LEFT, padx=5)
        
        self.pause_button = ttk.Button(control_frame, text="Pause", command=self.toggle_pause, state=tk.DISABLED)
        self.pause_button.pack(side=tk.LEFT, padx=5)
        
        self.stop_button = ttk.Button(control_frame, text="Stop", command=self.stop_search, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5)
        
        # Progress section
        progress_frame = ttk.LabelFrame(main_frame, text="Progress", padding="10")
        progress_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Create columns for statistics
        stats_frame = ttk.Frame(progress_frame)
        stats_frame.pack(fill=tk.BOTH, expand=True)
        
        # Progress display
        self.progress_text = scrolledtext.ScrolledText(stats_frame, height=10)
        self.progress_text.pack(fill=tk.BOTH, expand=True)
        
        # Current status
        status_frame = ttk.Frame(main_frame)
        status_frame.pack(fill=tk.X, pady=5)
        
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(status_frame, textvariable=self.status_var).pack(side=tk.LEFT)
        
        # URL count
        self.url_count_var = tk.StringVar(value="URLs found: 0 | Valid URLs: 0")
        ttk.Label(status_frame, textvariable=self.url_count_var).pack(side=tk.RIGHT)

    def load_dorks_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as file:
                    content = file.read()
                    self.dork_text.delete(1.0, tk.END)
                    self.dork_text.insert(tk.END, content)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load file: {str(e)}")

    def get_random_user_agent(self):
        return {'User-Agent': random.choice(self.user_agents),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Referer': 'https://www.google.com/',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'}

    def start_search(self):
        # Get dorks from text area
        dork_text = self.dork_text.get(1.0, tk.END).strip()
        if not dork_text:
            messagebox.showwarning("Warning", "Please add at least one dork.")
            return
            
        dorks = [d.strip() for d in dork_text.split('\n') if d.strip()]
        
        # Check if at least one engine is selected
        selected_engines = [engine for engine, var in self.engine_vars.items() if var.get()]
        if not selected_engines:
            messagebox.showwarning("Warning", "Please select at least one search engine.")
            return
            
        # Reset variables
        self.is_running = True
        self.is_paused = False
        self.valid_urls = []
        self.current_dork_index = 0
        self.engine_stats = {engine: {'total': 0, 'valid': 0} for engine in self.search_engines.keys()}
        
        # Update UI state
        self.start_button.config(state=tk.DISABLED)
        self.pause_button.config(state=tk.NORMAL, text="Pause")
        self.stop_button.config(state=tk.NORMAL)
        self.progress_text.delete(1.0, tk.END)
        self.status_var.set("Running...")
        
        # Create worker threads
        num_threads = self.thread_var.get()
        self.active_threads = []
        
        # Launch worker threads
        for _ in range(num_threads):
            thread = threading.Thread(target=self.worker, args=(dorks, selected_engines), daemon=True)
            thread.start()
            self.active_threads.append(thread)
            
        # Monitoring thread
        monitor_thread = threading.Thread(target=self.monitor_progress, daemon=True)
        monitor_thread.start()

    def worker(self, dorks, selected_engines):
        while self.is_running:
            # Get next dork
            with self.lock:
                if self.current_dork_index >= len(dorks):
                    return
                dork_index = self.current_dork_index
                self.current_dork_index += 1
                
            dork = dorks[dork_index]
            encoded_dork = quote_plus(dork)
            
            # Check if paused
            while self.is_paused and self.is_running:
                time.sleep(0.5)
                
            if not self.is_running:
                return
                
            # Process each selected engine
            for engine_name in selected_engines:
                engine_config = self.search_engines[engine_name]
                
                # Process multiple pages for deeper search
                for page in range(engine_config['max_pages']):
                    if not self.is_running:
                        return
                        
                    # Check if paused
                    while self.is_paused and self.is_running:
                        time.sleep(0.5)
                        
                    try:
                        # Get URL for this page
                        url = engine_config['url'](encoded_dork, page)
                        
                        # Add a delay to avoid rate limiting
                        time.sleep(random.uniform(1.0, 3.0))
                        
                        # Make request
                        headers = self.get_random_user_agent()
                        response = requests.get(url, headers=headers, timeout=15)
                        
                        if response.status_code == 200:
                            # Parse results using engine-specific parser
                            found_urls = engine_config['parser'](response.text)
                            
                            # Filter and validate URLs
                            valid_found = self.filter_urls(found_urls)
                            
                            # Update stats
                            with self.lock:
                                self.engine_stats[engine_name]['total'] += len(found_urls)
                                self.engine_stats[engine_name]['valid'] += len(valid_found)
                                self.valid_urls.extend(valid_found)
                            
                            # Update queue
                            self.results_queue.put({
                                'engine': engine_name,
                                'dork': dork,
                                'total': len(found_urls),
                                'valid': len(valid_found),
                                'page': page + 1
                            })
                            
                            # If no results found on this page, stop paginating
                            if len(found_urls) == 0:
                                break
                                
                    except Exception as e:
                        # Log error but continue
                        self.results_queue.put({
                            'engine': engine_name,
                            'dork': dork,
                            'error': str(e)
                        })

    def toggle_pause(self):
        self.is_paused = not self.is_paused
        if self.is_paused:
            self.pause_button.config(text="Resume")
            self.status_var.set("Paused")
        else:
            self.pause_button.config(text="Pause")
            self.status_var.set("Running...")

    def stop_search(self):
        if not self.is_running:
            return
            
        self.is_running = False
        self.status_var.set("Stopping...")
        
        # Wait for threads to finish
        for thread in self.active_threads:
            if thread.is_alive():
                thread.join(0.1)
                
        # Save results
        if self.valid_urls:
            self.save_results()
            
        # Update UI
        self.start_button.config(state=tk.NORMAL)
        self.pause_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.DISABLED)
        self.status_var.set("Search completed")
        
        # Show summary
        messagebox.showinfo("Search Completed", f"Total valid URLs found: {len(self.valid_urls)}")

    def monitor_progress(self):
        """Monitor thread progress and handle completion"""
        while self.is_running and any(t.is_alive() for t in self.active_threads):
            time.sleep(0.5)
            
        if self.is_running:  # If not manually stopped
            self.stop_search()

    def update_from_queue(self):
        """Update UI with data from the results queue"""
        try:
            # Process up to 10 items per update to keep UI responsive
            for _ in range(10):
                if self.results_queue.empty():
                    break
                    
                result = self.results_queue.get_nowait()
                
                if 'error' in result:
                    # Log error
                    self.log_message(f"Error in {result['engine']} for dork '{result['dork']}': {result['error']}")
                else:
                    # Log success
                    self.log_message(
                        f"{result['engine']} - Dork: '{result['dork']}' - "
                        f"Page {result['page']} - Found: {result['total']} - Valid: {result['valid']}"
                    )
                
                self.results_queue.task_done()
        except queue.Empty:
            pass
            
        # Update URL count
        total_urls = sum(stats['total'] for stats in self.engine_stats.values())
        total_valid = sum(stats['valid'] for stats in self.engine_stats.values())
        self.url_count_var.set(f"URLs found: {total_urls} | Valid URLs: {total_valid}")
        
        # Schedule next update
        self.root.after(100, self.update_from_queue)

    def log_message(self, message):
        """Add a message to the progress text area"""
        self.progress_text.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] {message}\n")
        self.progress_text.see(tk.END)

    def save_results(self):
        """Save valid URLs to a text file"""
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"results_{timestamp}.txt"
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                for url in self.valid_urls:
                    f.write(f"{url}\n")
            self.log_message(f"Results saved to {filename}")
        except Exception as e:
            self.log_message(f"Error saving results: {str(e)}")

    def filter_urls(self, urls):
        """Filter and validate URLs"""
        # Exclude search engine domains and other unwanted URLs
        excluded_domains = [
            'google.com', 'bing.com', 'yahoo.com', 'duckduckgo.com', 'aol.com',
            'yandex.com', 'naver.com', 'youtube.com', 'facebook.com', 'twitter.com',
            'instagram.com', 'linkedin.com', 'pinterest.com'
        ]
        
        valid_urls = []
        for url in urls:
            # Skip URLs from excluded domains
            if any(domain in url.lower() for domain in excluded_domains):
                continue
                
            # Basic URL validation
            if not url.startswith(('http://', 'https://')):
                continue
                
            # Add URL if it's not already in the list
            if url not in self.valid_urls and url not in valid_urls:
                valid_urls.append(url)
                
        return valid_urls

    # Parser functions for different search engines
    def parse_bing(self, html_content):
        soup = BeautifulSoup(html_content, 'html.parser')
        urls = []
        
        # Find all search results
        for result in soup.select('li.b_algo h2 a'):
            if 'href' in result.attrs:
                urls.append(result['href'])
                
        return urls

    def parse_duckduckgo(self, html_content):
        soup = BeautifulSoup(html_content, 'html.parser')
        urls = []
        
        # Find all result links
        for result in soup.select('.result__a'):
            if 'href' in result.attrs:
                href = result['href']
                if href.startswith('/'):
                    continue
                urls.append(href)
                
        return urls

    def parse_yahoo(self, html_content):
        soup = BeautifulSoup(html_content, 'html.parser')
        urls = []
        
        # Find all result links
        for result in soup.select('.algo-sr a'):
            if 'href' in result.attrs:
                urls.append(result['href'])
                
        return urls

    def parse_aol(self, html_content):
        soup = BeautifulSoup(html_content, 'html.parser')
        urls = []
        
        # Find all result links
        for result in soup.select('.algo-sr a'):
            if 'href' in result.attrs:
                urls.append(result['href'])
                
        return urls

    def parse_google_api(self, json_content):
        # This would parse JSON from Google API
        # Note: This requires proper API key setup
        try:
            data = json.loads(json_content)
            urls = []
            if 'items' in data:
                for item in data['items']:
                    if 'link' in item:
                        urls.append(item['link'])
            return urls
        except:
            return []

    def parse_bing_news(self, html_content):
        soup = BeautifulSoup(html_content, 'html.parser')
        urls = []
        
        # Find all news result links
        for result in soup.select('.news-card a'):
            if 'href' in result.attrs:
                urls.append(result['href'])
                
        return urls

    def parse_naver(self, html_content):
        soup = BeautifulSoup(html_content, 'html.parser')
        urls = []
        
        # Find all result links
        for result in soup.select('.total_wrap a.link_tit'):
            if 'href' in result.attrs:
                urls.append(result['href'])
                
        return urls

    def parse_yandex(self, html_content):
        soup = BeautifulSoup(html_content, 'html.parser')
        urls = []
        
        # Find all result links
        for result in soup.select('.organic__url'):
            if 'href' in result.attrs:
                urls.append(result['href'])
                
        return urls

# Run the application
if __name__ == "__main__":
    # Import missing modules
    import json
    
    root = tk.Tk()
    app = DorkParser(root)
    root.mainloop()
