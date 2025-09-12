import os
import re
from urllib.parse import urljoin, urlparse
import random

# Import gevent and patch BEFORE importing other libraries
import gevent.monkey
gevent.monkey.patch_all()

from locust import HttpUser, task, between
import requests
from bs4 import BeautifulSoup


# --- Configuration ---
TARGET_HOST = os.getenv("TARGET_HOST", "https://docs.locust.io")


# --- Lists for Test Data ---
SEARCH_QUERIES = [
    # Original Terms
    "shirt", "shoes", "pants", "jacket", "hat", "socks", "dress", "gear",
    # 100+ New Apparel Terms
    "t-shirt", "jeans", "sweater", "hoodie", "shorts", "skirt", "blouse",
    "leggings", "coat", "blazer", "vest", "cardigan", "pullover", "tank top",
    "polo shirt", "suit", "trousers", "joggers", "tracksuit", "overalls",
    "jumpsuit", "romper", "kimono", "poncho", "scarf", "gloves", "beanie",
    "cap", "belt", "tie", "bowtie", "suspenders", "sneakers", "boots",
    "sandals", "heels", "flats", "loafers", "slippers", "swimsuit", "bikini",
    "trunks", "pajamas", "robe", "underwear", "bra", "briefs", "boxers",
    "tights", "stockings", "athletic shorts", "sports bra", "yoga pants",
    "windbreaker", "fleece jacket", "denim jacket", "leather jacket",
    "trench coat", "parka", "bomber jacket", "peacoat", "duffle coat",
    "button-down shirt", "flannel shirt", "henley shirt", "v-neck",
    "crewneck", "turtleneck", "maxi dress", "midi dress", "mini dress",
    "sundress", "cocktail dress", "formal gown", "pencil skirt", "a-line skirt",
    "pleated skirt", "cargo pants", "chinos", "corduroys", "capris",
 "culottes", "wide-leg pants", "straight-leg jeans", "skinny jeans",
    "bootcut jeans", "high-waisted jeans", "mom jeans", "boyfriend jeans",
    "graphic tee", "tunic", "camisole", "bodysuit", "Ankle boots",
    "Chelsea boots", "hiking boots", "running shoes", "cross-trainers",
    "espadrilles", "wedges", "pumps", "oxfords", "derby shoes", "clogs"
]
COLORS = [
    # Original Colors
    "red", "blue", "green", "black", "white", "yellow", "purple",
    # Expanded List of Colors
    "navy", "sky blue", "royal blue", "teal", "turquoise", "cyan",
    "forest green", "lime", "olive", "mint", "gray", "silver", "charcoal",
    "ivory", "cream", "beige", "tan", "brown", "maroon", "burgundy",
    "crimson", "scarlet", "pink", "magenta", "fuchsia", "lavender",
    "violet", "indigo", "orange", "gold", "coral", "salmon", "peach",
    "khaki", "plum", "mustard", "ochre", "rose gold", "bronze", "copper"
]
SIZES = [
    "XS", "S", "M", "L", "XL", "XXL"
]



class WebsiteUser(HttpUser):
    """
    A user class that simulates a user browsing a website.
    
    This user will first crawl the website to discover internal URLs on start,
    and then randomly visit those discovered URLs as its main task.
    """
    wait_time = between(1, 5)
    host = TARGET_HOST

    def on_start(self):
        """
        Called when a user is started. This is where we'll crawl the site.
        """
        print(f"Starting crawl on {self.host}")
        try:
            self.discovered_urls = self._crawl_website(self.host)
            if not self.discovered_urls:
                print("Warning: No URLs discovered. Adding root path.")
                self.discovered_urls = ["/"]
            else:
                print(f"Discovered {len(self.discovered_urls)} URLs.")
        except Exception as e:
            print(f"Error during crawling: {e}")
            self.discovered_urls = ["/"]  # Fallback to root

    def _crawl_website(self, base_url: str, max_pages: int = 50) -> list[str]:
        """
        Crawls a website to find all unique, internal URLs.
        
        Args:
            base_url: The starting URL to crawl.
            max_pages: Maximum number of pages to crawl to prevent infinite loops.
            
        Returns:
            A list of unique URLs found on the site.
        """
        discovered_paths = set(["/"])
        to_crawl = ["/"]
        crawled_count = 0
        base_netloc = urlparse(base_url).netloc

        # Use a session for better connection reuse
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Locust-Crawler/1.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        })
        
        # Set reasonable timeouts and disable SSL verification if needed
        session.timeout = (10, 30)  # (connect, read) timeouts
        session.verify = True  # Set to False if you have SSL issues

        while to_crawl and crawled_count < max_pages:
            path = to_crawl.pop(0)
            crawled_count += 1
            
            try:
                # Use the session instead of self.client for crawling
                full_url = urljoin(base_url, path)
                print(f"Crawling: {path}")
                
                response = session.get(full_url)
                response.raise_for_status()
                
                # Only parse HTML content
                content_type = response.headers.get('content-type', '').lower()
                if 'text/html' not in content_type:
                    continue
                    
            except Exception as e:
                print(f"Crawler request failed for {path}: {e}")
                continue

            try:
                soup = BeautifulSoup(response.text, "html.parser")

                for link in soup.find_all("a", href=True):
                    href = link['href'].strip()

                    # Clean up the URL
                    if "#" in href:
                        href = href.split("#")[0]
                    if not href or href.startswith(("mailto:", "tel:", "javascript:")):
                        continue

                    # Make URL absolute and parse it
                    absolute_url = urljoin(full_url, href)
                    parsed_url = urlparse(absolute_url)

                    # Check if it's an internal link and not a static asset
                    if (parsed_url.netloc == base_netloc and 
                        not self._is_static_asset(parsed_url.path) and
                        parsed_url.path not in discovered_paths):
                        
                        discovered_paths.add(parsed_url.path)
                        if len(to_crawl) < 20:  # Limit queue size
                            to_crawl.append(parsed_url.path)

            except Exception as e:
                print(f"Error parsing HTML for {path}: {e}")
                continue

        session.close()
        return list(discovered_paths)

    def _is_static_asset(self, path: str) -> bool:
        """
        Check if a URL path points to a common static file type.
        """
        static_extensions = r"\.(css|js|png|jpg|jpeg|gif|svg|ico|woff|woff2|ttf|eot|pdf|zip|gz|mp4|webm|xml|json)$"
        return bool(re.search(static_extensions, path, re.IGNORECASE))

    @task(3)
    def visit_random_page(self):
        """
        A task that simulates a user visiting a random discovered page.
        """
        if self.discovered_urls:
            # Use random.choice for better randomization
            path_to_visit = random.choice(self.discovered_urls)
            try:
                with self.client.get(path_to_visit, catch_response=True) as response:
                    if response.status_code != 200:
                        response.failure(f"Got status code {response.status_code}")
            except Exception as e:
                print(f"Request failed for {path_to_visit}: {e}")
        else:
            # Fallback if no URLs discovered
            self.client.get("/")

    @task(2)
    def search_basic(self):
        """
        Simulates a user performing a basic search.
        Adapts to different search patterns found during crawling.
        """
        if hasattr(self, 'search_info') and self.search_info.get('has_search'):
            self._perform_detected_search()
        else:
            self._perform_common_search_patterns()

    @task(1)
    def search_with_filters(self):
        """
        Simulates a user searching with additional filters/parameters.
        """
        if hasattr(self, 'search_info') and self.search_info.get('has_search'):
            self._perform_filtered_search()
        else:
            self._perform_ecommerce_search()

    def _perform_detected_search(self):
        """
        Perform search using patterns detected during crawling.
        Returns the response for URL discovery.
        """
        search_path = random.choice(self.search_info['search_paths'])
        param_name = self.search_info['search_params'][0] if self.search_info['search_params'] else 'q'
        
        # Choose appropriate search terms based on detected patterns
        if 'catalogsearch' in search_path.lower() or any('catalog' in path for path in self.search_info['search_paths']):
            query = random.choice(SEARCH_QUERIES)
        else:
            query = random.choice(GENERIC_SEARCH_TERMS)
        
        url = f"{search_path}?{param_name}={query}"
        response = self.client.get(url, name="detected_search")
        return response

    def _perform_filtered_search(self):
        """
        Perform search with filters using detected patterns.
        Returns the response for URL discovery.
        """
        search_path = random.choice(self.search_info['search_paths'])
        param_name = self.search_info['search_params'][0] if self.search_info['search_params'] else 'q'
        
        query = random.choice(SEARCH_QUERIES)
        color = random.choice(COLORS)
        size = random.choice(SIZES)
        
        url = f"{search_path}?{param_name}={query}&color={color}&size={size}"
        response = self.client.get(url, name="filtered_search")
        return response

    def _perform_common_search_patterns(self):
        """
        Try common search URL patterns when no specific pattern is detected.
        Returns the response for URL discovery.
        """
        query = random.choice(GENERIC_SEARCH_TERMS)
        
        # Try common search URL patterns
        search_patterns = [
            f"/search?q={query}",
            f"/search/?query={query}",
            f"/?s={query}",
            f"/s/{query}",
            f"/find?q={query}"
        ]
        
        search_url = random.choice(search_patterns)
        try:
            with self.client.get(search_url, catch_response=True, name="generic_search") as response:
                if response.status_code == 404:
                    response.failure("Search endpoint not found")
                    return None
                return response
        except Exception as e:
            print(f"Generic search failed: {e}")
            return None

    def _perform_ecommerce_search(self):
        """
        Perform ecommerce-style search with filters.
        Returns the response for URL discovery.
        """
        query = random.choice(SEARCH_QUERIES)
        color = random.choice(COLORS)
        size = random.choice(SIZES)
        
        # Try common ecommerce search patterns
        ecommerce_patterns = [
            f"/catalogsearch/result/?q={query}",
            f"/search?q={query}&color={color}&size={size}",
            f"/products/search?query={query}&filters[color]={color}",
            f"/shop?search={query}&color={color}&size={size}"
        ]
        
        search_url = random.choice(ecommerce_patterns)
        try:
            with self.client.get(search_url, catch_response=True, name="ecommerce_search") as response:
                if response.status_code == 404:
                    response.failure("Ecommerce search endpoint not found")
                    return None
                return response
        except Exception as e:
            print(f"Ecommerce search failed: {e}")
            return None

    @task(1)  # Lower weight task
    def visit_homepage(self):
        """
        Occasionally visit the homepage to simulate typical user behavior.
        """
        self.client.get("/")
