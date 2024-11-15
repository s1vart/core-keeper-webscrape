import requests
from bs4 import BeautifulSoup
import json
import time
from typing import Dict, List

class CoreKeeperAccessoryScraper:
    def __init__(self):
        self.base_url = "https://core-keeper.fandom.com"
        self.accessories_url = f"{self.base_url}/wiki/Accessories"
        self.items_data = {
            "rings": {},
            "necklaces": {},
            "off-hand": {},
            "bags": {},
            "lanterns": {}
        }
        self.scraped_urls = set()
        self.debug_mode = False
    
    def get_page(self, url: str) -> BeautifulSoup:
        time.sleep(1)  # Add delay to be nice to the wiki
        response = requests.get(url)
        return BeautifulSoup(response.content, 'html.parser')
    
    def scrape_accessory_page(self, accessory_url: str, accessory_type: str) -> Dict:
        soup = self.get_page(accessory_url)
        accessory_data = {
            'name': '',
            'type': accessory_type,
            'category': [],
            'min_level': None,
            'max_level': None,
            'levels': {},  # Will store data for each level
            'url': accessory_url,
            'set_bonus': {
                'required_items': [],
                'bonuses': {}
            }
        }
        try:
            # Get accessory name
            accessory_data['name'] = soup.find('h1', {'id': 'firstHeading'}).text.strip()
            print(f"\nProcessing accessory: {accessory_data['name']}")
            # Find the infobox
            infobox = soup.find('aside', {'class': 'portable-infobox'})
            if infobox:
                # First process basic info
                for label in infobox.find_all('div', {'class': 'pi-item'}):
                    label_name = label.find('div', {'class': 'pi-data-label'})
                    label_value = label.find('div', {'class': 'pi-data-value'})
                    if label_name and label_value:
                        key = label_name.text.strip().lower()
                        value = label_value.text.strip()
                        if key == 'category':
                            accessory_data['category'] = [cat.strip() for cat in value.split(',')]
                
                # Now find set bonus section specifically
                set_sections = infobox.find_all('section', {'class': 'pi-item'})
                for section in set_sections:
                    header = section.find('h2', {'class': 'pi-header'})
                    if header and 'set bonus' in header.text.strip().lower():
                        bonus_div = section.find('div', {'class': 'pi-data-value pi-font'})
                        if bonus_div:
                            # Get all set bonus effects - they are direct child divs
                            bonus_texts = bonus_div.find_all('div', recursive=False)
                            for bonus_text_div in bonus_texts:
                                bonus_text = bonus_text_div.text.strip()
                                if 'set:' in bonus_text.lower():
                                    # Extract the set size and effect
                                    parts = bonus_text.lower().split('set:', 1)
                                    set_size = ''.join(filter(str.isdigit, parts[0]))
                                    effect = parts[1].strip()
                                    if set_size:
                                        accessory_data['set_bonus']['bonuses'][set_size] = effect
                            
                            # Get the required items directly from the text
                            items_list = bonus_div.find('ul')
                            if items_list:
                                for item_li in items_list.find_all('li'):
                                    item_name = item_li.text.strip()
                                    if item_name and item_name != accessory_data['name']:
                                        accessory_data['set_bonus']['required_items'].append(item_name)
                
                # First, find all available levels from the tabs
                tabs_list = infobox.find('ul', {'class': 'wds-tabs'})
                available_levels = []
                if tabs_list:
                    for tab in tabs_list.find_all('div', {'class': 'wds-tabs__tab-label'}):
                        level_text = tab.text.strip()
                        if level_text.isdigit() or 'Level' in level_text:
                            level_num = ''.join(filter(str.isdigit, level_text))
                            if level_num:
                                available_levels.append(int(level_num))
                
                if available_levels:
                    accessory_data['min_level'] = min(available_levels)
                    accessory_data['max_level'] = max(available_levels)
                    print(f"Found levels from {accessory_data['min_level']} to {accessory_data['max_level']}")
                    
                    # Find all tab content sections
                    tab_contents = infobox.find_all('div', {'class': 'wds-tab__content'})
                    for content in tab_contents:
                        level_data = {}
                        data_items = content.find_all('div', {'class': 'pi-item pi-data pi-item-spacing pi-border-color'})
                        for item in data_items:
                            label = item.find('h3', {'class': 'pi-data-label pi-secondary-font'})
                            value = item.find('div', {'class': 'pi-data-value pi-font'})
                            if label and value:
                                key = label.text.strip().lower()
                                val = value.text.strip()
                                if '(' in val:
                                    val = val.split('(')[0].strip()
                                level_data[key] = val
                        
                        if 'level' in level_data:
                            level_num = level_data['level']
                            accessory_data['levels'][level_num] = level_data
                            print(f"Processed level {level_num} data")
                else:
                    print(f"No level data found for {accessory_data['name']}")
        except Exception as e:
            print(f"Error scraping {accessory_url}: {str(e)}")
        return accessory_data
    
    def scrape_accessories(self, debug_mode=False):
        self.debug_mode = debug_mode
        print(f"Starting to scrape accessories from {self.accessories_url}")
        print(f"Debug mode: {'ON' if debug_mode else 'OFF'}")
        try:
            soup = self.get_page(self.accessories_url)
            print("Successfully loaded the accessories page")
            tables = soup.find_all('table', {'class': 'fandom-table'})
            print(f"Found {len(tables)} tables")
            
            # List of URLs to skip - these are armor/other equipment pages
            skip_urls = [
                '/wiki/Diving_Helm',
                '/wiki/Kelp_Mantle',
                '/wiki/Scuba_Fins',
                'Category:Armor',
                'Category:Equipment'
            ]
            
            for table in tables:
                header = table.find_previous(['h2', 'h3'])
                if not header:
                    continue
                    
                section_text = header.get_text().strip()
                print(f"\nProcessing section: {section_text}")
                
                current_category = None
                if "Rings" in section_text:
                    current_category = "rings"
                elif "Necklaces" in section_text:
                    current_category = "necklaces"
                elif "Off-hand" in section_text:
                    current_category = "off-hand"
                elif "Bags" in section_text:
                    current_category = "bags"
                elif "Lanterns" in section_text:
                    current_category = "lanterns"
                
                if not current_category:
                    continue
                    
                print(f"Found category: {current_category}")
                
                for cell in table.find_all('td'):
                    item_spans = cell.find_all('span', {'class': 'item'})
                    for item_span in item_spans:
                        link = item_span.find('a', href=True)
                        if link and link.get('href'):
                            href = link.get('href')
                            
                            # Skip if the URL matches any in our skip list
                            if any(skip_url in href for skip_url in skip_urls):
                                print(f"  Skipping non-accessory item: {href}")
                                continue
                                
                            # Only process links that are specifically to accessories
                            if not ('/wiki/Accessories/' in href or 
                                  'Category:Accessories' in href or
                                  any(f'_{cat}' in href.lower() for cat in ['ring', 'necklace', 'lantern', 'bag'])):
                                print(f"  Skipping non-accessory link: {href}")
                                continue
                            
                            if href and not href.startswith('#'):
                                if href.startswith('/'):
                                    accessory_url = self.base_url + href
                                elif href.startswith('http'):
                                    accessory_url = href
                                else:
                                    accessory_url = f"{self.base_url}/{href}"
                                
                                if accessory_url in self.scraped_urls:
                                    print(f"  Skipping already scraped accessory: {accessory_url}")
                                    continue
                                
                                print(f"  Scraping accessory: {accessory_url}")
                                accessory_data = self.scrape_accessory_page(accessory_url, current_category)
                                if accessory_data['name']:
                                    self.items_data[current_category][accessory_data['name']] = accessory_data
                                    self.scraped_urls.add(accessory_url)
                                
                                if self.debug_mode:
                                    print("Debug mode: Stopping after first accessory")
                                    return
                                    
        except Exception as e:
            print(f"Error in scrape_accessories: {str(e)}")
            print("Full error:")
            import traceback
            traceback.print_exc()
    
    def save_to_json(self, filename: str = 'core_keeper_accessories.json'):
        """Save scraped data to JSON file"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.items_data, f, indent=2)

if __name__ == "__main__":
    scraper = CoreKeeperAccessoryScraper()
    scraper.scrape_accessories(debug_mode=False)
    scraper.save_to_json() 


