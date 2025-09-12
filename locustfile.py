import locust

import gevent.monkey
gevent.monkey.patch_all()


from locust import HttpUser, task, between


import os
import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup



# --- Configuration ---
# The host to be tested should be set via the TARGET_HOST environment variable.
# It defaults to a safe example if the variable is not set.
TARGET_HOST = os.getenv("TARGET_HOST", "https://docs.locust.io")

class WebsiteUser(HttpUser):
    """
    A user class that simulates a user browsing a website.

    This user will first crawl the website to discover internal URLs on start,
    and then randomly visit those discovered URLs as its main task.
    """
    wait_time = between(1, 5)  # Wait 1-5 seconds between tasks
    host = TARGET_HOST

    def on_start(self):
        """
        Called when a user is started. This is where we'll crawl the site.
        """
        print(f"Starting crawl on {self.host}")
        self.discovered_urls = self._crawl_website(self.host)
        if not self.discovered_urls:
            print("Warning: No URLs discovered. User will have no tasks to run.")
            # Quit the user if no URLs are found to avoid errors
            self.environment.runner.quit()
        else:
            print(f"Discovered {len(self.discovered_urls)} URLs.")

    def _crawl_website(self, base_url: str) -> list[str]:
        """
        Crawls a website to find all unique, internal URLs.

        Args:
            base_url: The starting URL to crawl.

        Returns:
            A list of unique URLs found on the site.
        """
        discovered_paths = set(["/"])
        to_crawl = ["/"]
        base_netloc = urlparse(base_url).netloc

        headers = {
            "User-Agent": "Locust-Crawler/1.0"
        }

        while to_crawl:
            path = to_crawl.pop(0)
            full_url = urljoin(base_url, path)

            try:
                response = self.client.get(path, headers=headers, name="Crawler")
                response.raise_for_status() # Raise an exception for bad status codes
            except requests.exceptions.RequestException as e:
                print(f"Crawler request failed for {full_url}: {e}")
                continue

            soup = BeautifulSoup(response.text, "html.parser")

            for link in soup.find_all("a", href=True):
                href = link['href']

                # Clean up the URL
                if "#" in href:
                    href = href.split("#")[0]
                if not href or href.startswith("mailto:") or href.startswith("tel:"):
                    continue

                # Make URL absolute and parse it
                absolute_url = urljoin(full_url, href)
                parsed_url = urlparse(absolute_url)

                # Check if it's an internal link and not a static asset
                if parsed_url.netloc == base_netloc and not self._is_static_asset(parsed_url.path):
                    if parsed_url.path not in discovered_paths:
                        discovered_paths.add(parsed_url.path)
                        to_crawl.append(parsed_url.path)

        return list(discovered_paths)

    def _is_static_asset(self, path: str) -> bool:
        """
        Check if a URL path points to a common static file type.
        """
        # Regex to match common static file extensions
        static_extensions = r"\.(css|js|png|jpg|jpeg|gif|svg|ico|woff|woff2|ttf|eot|pdf|zip|gz|mp4|webm)$"
        return bool(re.search(static_extensions, path, re.IGNORECASE))

    @task
    def visit_random_page(self):
        """
        A task that simulates a user visiting a random discovered page.
        """
        if self.discovered_urls:
            # Pick a random path from the discovered URLs
            path_to_visit = self.discovered_urls[
                (hash(str(self.environment.runner.stats.total.num_requests)) % len(self.discovered_urls))
            ]
            self.client.get(path_to_visit)
