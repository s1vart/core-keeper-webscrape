import os
import json
import requests
import time
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import logging

class CoreKeeperImageScraper:
    def __init__(self):
        self.base_url = "https://core-keeper.fandom.com"
        
        # Use relative paths from the scrapers directory
        self.images_dir = "../scraped_images"
        self.json_dir = "../scraped_json"
        
        self.delay = 1  # Delay between requests to be nice to the server
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
        
        # Ensure base images directory exists
        os.makedirs(self.images_dir, exist_ok=True)
        
        # Track processed URLs to avoid duplicates
        self.processed_urls = set()

    def get_page(self, url):
        """Fetch page content with error handling and delay"""
        try:
            time.sleep(self.delay)
            response = requests.get(url)
            response.raise_for_status()
            return BeautifulSoup(response.content, 'html.parser')
        except Exception as e:
            self.logger.error(f"Error fetching {url}: {str(e)}")
            return None

    def download_image(self, image_url, item_name, category_path):
        """Download image with error handling"""
        if not image_url or image_url in self.processed_urls:
            return False
            
        try:
            time.sleep(self.delay)
            response = requests.get(image_url)
            response.raise_for_status()
            
            # Clean filename and determine extension
            clean_name = "".join(c for c in item_name if c.isalnum() or c in (' ', '-', '_')).strip()
            ext = image_url.split('.')[-1].lower()
            if ext not in ['jpg', 'jpeg', 'png', 'gif']:
                ext = 'png'  # Default to png if extension is unusual
                
            # Create category directory if it doesn't exist
            category_dir = os.path.join(self.images_dir, category_path)
            os.makedirs(category_dir, exist_ok=True)
            
            filename = f"{clean_name}.{ext}"
            filepath = os.path.join(category_dir, filename)
            
            with open(filepath, 'wb') as f:
                f.write(response.content)
                
            self.processed_urls.add(image_url)
            self.logger.info(f"Downloaded image for {item_name} to {category_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error downloading image for {item_name}: {str(e)}")
            return False

    def scrape_item_image(self, item_url, item_name, category_path):
        """Scrape image for a specific item"""
        soup = self.get_page(item_url)
        if not soup:
            return False
            
        # Look for the main item image
        image = soup.find('figure', class_='pi-item pi-image')
        if image:
            img_tag = image.find('img')
            if img_tag and 'src' in img_tag.attrs:
                image_url = img_tag['src']
                # Remove thumbnail parameters if present
                image_url = image_url.split('/revision/')[0]
                return self.download_image(image_url, item_name, category_path)
                
        return False

    def scrape_all_images(self):
        """Main function to scrape images for all items"""
        json_files = [f for f in os.listdir(self.json_dir) if f.endswith('.json')]
        
        for json_file in json_files:
            self.logger.info(f"Processing {json_file}")
            
            try:
                with open(os.path.join(self.json_dir, json_file), 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Get base category from filename (e.g., "accessories" from "core_keeper_accessories.json")
                base_category = json_file.replace('core_keeper_', '').replace('.json', '')
                
                # Handle different JSON structures
                if isinstance(data, dict):
                    # For nested structures (like weapons.json)
                    for category_name, category_items in data.items():
                        if isinstance(category_items, dict):
                            # Create category path (e.g., "accessories/rings")
                            category_path = os.path.join(base_category, category_name)
                            
                            for item_name, item_data in category_items.items():
                                if isinstance(item_data, dict) and 'url' in item_data:
                                    self.scrape_item_image(item_data['url'], item_name, category_path)
                                    
                elif isinstance(data, list):
                    # For flat structures
                    for item in data:
                        if isinstance(item, dict) and 'url' in item:
                            self.scrape_item_image(item['url'], item['name'], base_category)
                            
            except Exception as e:
                self.logger.error(f"Error processing {json_file}: {str(e)}")

def main():
    scraper = CoreKeeperImageScraper()
    scraper.scrape_all_images()

if __name__ == "__main__":
    main() 