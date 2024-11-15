import requests
from bs4 import BeautifulSoup
import json
import time
from typing import Dict, List
import re

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
        self.skip_urls = [
            '/wiki/Diving_Helm',
            '/wiki/Kelp_Mantle',
            '/wiki/Scuba_Fins',
            'Category:Armor',
            'Category:Equipment'
        ]
    
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
                    
                    # Track processed levels to avoid duplicates
                    processed_levels = set()
                    
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
                                
                                # Clean up level numbers and effects for ALL fields
                                val = re.sub(r'\s*\([^)]*\)', '', val).strip()
                                
                                # Additional processing for effects
                                if key == 'effects':
                                    effects = ['+' + e.strip() for e in val.split('+') if e.strip()]
                                    if effects and effects[0].startswith('++'):
                                        effects[0] = effects[0][1:]
                                    val = ''.join(effects)
                                
                                level_data[key] = val
                        
                        if 'level' in level_data:
                            level_num = level_data['level']
                            # Only process this level if we haven't seen it before
                            if level_num not in processed_levels:
                                accessory_data['levels'][level_num] = level_data
                                processed_levels.add(level_num)
                                print(f"Processed level {level_num} data")
                else:
                    print(f"No level data found for {accessory_data['name']}")
        except Exception as e:
            print(f"Error scraping {accessory_url}: {str(e)}")
        return accessory_data
    
    def scrape_accessories(self, debug_mode=False):
        self.debug_mode = debug_mode
        processed_count = 0
        
        try:
            soup = self.get_page(self.accessories_url)
            sections = soup.find_all(['h2', 'h3'])
            urls_to_scrape = []
            queued_urls = set()  # Add this to track URLs already in queue
            
            for section in sections:
                table = section.find_next('table', {'class': 'fandom-table'})
                if not table:
                    continue
                    
                section_text = section.get_text().strip()
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
                    
                print(f"\nProcessing {current_category} table")
                
                for row in table.find_all('tr'):
                    first_cell = row.find('td')
                    if first_cell:
                        link = first_cell.find('a', href=True)
                        if link and link.get('href'):
                            href = link.get('href')
                            
                            if any(skip_url in href for skip_url in self.skip_urls):
                                continue
                            
                            if href and not href.startswith('#'):
                                if href.startswith('/'):
                                    accessory_url = self.base_url + href
                                elif href.startswith('http'):
                                    accessory_url = href
                                else:
                                    accessory_url = f"{self.base_url}/{href}"
                                
                                # Only add if URL is not in queue and not already scraped
                                if accessory_url not in queued_urls and accessory_url not in self.scraped_urls:
                                    urls_to_scrape.append((accessory_url, current_category))
                                    queued_urls.add(accessory_url)  # Add to queued set
            
            # Process URLs
            for accessory_url, current_category in urls_to_scrape:
                print(f"\nScraping accessory: {accessory_url}")
                accessory_data = self.scrape_accessory_page(accessory_url, current_category)
                if accessory_data['name']:
                    self.items_data[current_category][accessory_data['name']] = accessory_data
                    self.scraped_urls.add(accessory_url)
                    processed_count += 1
                    
                    if self.debug_mode and processed_count >= 3:
                        print("Debug mode: Stopping after third processed accessory")
                        self.save_to_json()  # Save before returning in debug mode
                        return
                    
        except Exception as e:
            print(f"Error in scrape_accessories: {str(e)}")
            traceback.print_exc()
        
        # Only save here if we're not in debug mode
        if not self.debug_mode:
            self.save_to_json()
    
    def save_to_json(self, filename: str = 'core_keeper_accessories.json'):
        """Save scraped data to JSON file"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.items_data, f, indent=2)
    
    def process_effects(self, effects_text):
        # Remove any (+X) or (-X) indicators
        effects = re.sub(r'\s*[\(\[]-?\+?\d+\.?\d*%?\)?]?', '', effects_text)
        return effects
    
    def scrape_levels(self, table_rows):
        levels = {}
        current_level = None
        
        for row in table_rows:
            cells = row.find_all(['th', 'td'])
            if len(cells) < 2:
                continue
            
            header = cells[0].get_text(strip=True)
            value = cells[1].get_text(strip=True)
            
            if header == 'Level':
                current_level = value
                levels[current_level] = {}
            elif current_level is not None:
                # For effects, process to remove change indicators but keep all effects
                if header == 'Effects':
                    value = self.process_effects(value)
                levels[current_level][header.lower()] = value
                
        return levels

if __name__ == "__main__":
    scraper = CoreKeeperAccessoryScraper()
    scraper.scrape_accessories(debug_mode=False)
