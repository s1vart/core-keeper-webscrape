import requests
from bs4 import BeautifulSoup
import json
import time
from typing import Dict, List

class CoreKeeperScraper:
    def __init__(self):
        self.base_url = "https://core-keeper.fandom.com"
        self.weapons_url = f"{self.base_url}/wiki/Weapons"
        self.items_data = {
            "melee": {},
            "range": {},
            "magic": {},
            "summon": {}
        }
        self.scraped_urls = set()
        self.debug_mode = False
        
    def get_page(self, url: str) -> BeautifulSoup:
        # Add delay to be nice to the wiki
        time.sleep(1)
        response = requests.get(url)
        return BeautifulSoup(response.content, 'html.parser')
    
    def scrape_weapon_page(self, weapon_url: str, weapon_type: str) -> Dict:
        soup = self.get_page(weapon_url)
        
        weapon_data = {
            'name': '',
            'type': weapon_type,
            'rarity': '',
            'base_attack_rate': '',
            'durability': '',
            'tooltip': '',
            'crafting_exp': '',
            'category': [],
            'min_level': None,
            'max_level': None,
            'levels': {},  # Will store data for each level
            'url': weapon_url
        }
        
        try:
            # Get weapon name
            weapon_data['name'] = soup.find('h1', {'id': 'firstHeading'}).text.strip()
            print(f"\nProcessing weapon: {weapon_data['name']}")
            
            # Find the infobox
            infobox = soup.find('aside', {'class': 'portable-infobox'})
            if infobox:
                # Get basic info
                for label in infobox.find_all('div', {'class': 'pi-item'}):
                    label_name = label.find('div', {'class': 'pi-data-label'})
                    label_value = label.find('div', {'class': 'pi-data-value'})
                    if label_name and label_value:
                        key = label_name.text.strip().lower()
                        value = label_value.text.strip()
                        
                        if key == 'category':
                            weapon_data['category'] = [cat.strip() for cat in value.split(',')]
                        elif key == 'attack rate':
                            weapon_data['base_attack_rate'] = value.replace(' per second', '')
                        elif key == 'tooltip':
                            weapon_data['tooltip'] = value
                        elif key == 'crafting exp':
                            weapon_data['crafting_exp'] = value
                        elif key == 'rarity':
                            weapon_data['rarity'] = value
                        elif key == 'durability':
                            weapon_data['durability'] = value
                
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
                    weapon_data['min_level'] = min(available_levels)
                    weapon_data['max_level'] = max(available_levels)
                    print(f"Found levels from {weapon_data['min_level']} to {weapon_data['max_level']}")
                    
                    # Find all tab content sections
                    tab_contents = infobox.find_all('div', {'class': 'wds-tab__content'})
                    
                    for content in tab_contents:
                        level_data = {}
                        
                        # Find all pi-item pi-data divs directly
                        data_items = content.find_all('div', {'class': 'pi-item pi-data pi-item-spacing pi-border-color'})
                        for item in data_items:
                            # Find the label (h3) and value (div) within this pi-item
                            label = item.find('h3', {'class': 'pi-data-label pi-secondary-font'})
                            value = item.find('div', {'class': 'pi-data-value pi-font'})
                            
                            if label and value:
                                key = label.text.strip().lower()
                                val = value.text.strip()
                                
                                # Clean up the value (remove upgrade notes in parentheses)
                                if '(' in val:
                                    val = val.split('(')[0].strip()
                                
                                # Special handling for certain fields
                                if key == 'level':
                                    level_num = ''.join(filter(str.isdigit, val))
                                elif key in ['range damage', 'melee damage', 'magic damage']:
                                    key = 'damage'  # normalize damage key
                                elif key == 'attack rate':
                                    val = val.replace(' per second', '')
                                elif key == 'effects':
                                    # Keep the percentage in effects
                                    val = val.split('(')[0].strip()
                                
                                level_data[key] = val
                        
                        # Only add the level data if we found a level number
                        if 'level' in level_data:
                            level_num = level_data['level']
                            weapon_data['levels'][level_num] = level_data
                            print(f"Processed level {level_num} data")
                
                else:
                    print(f"No level data found for {weapon_data['name']}")
    
        except Exception as e:
            print(f"Error scraping {weapon_url}: {str(e)}")
            
        return weapon_data
    
    def scrape_weapons(self, debug_mode=False):
        """
        Scrape all weapons from the weapons page
        Args:
            debug_mode (bool): If True, only scrape the first weapon found
        """
        self.debug_mode = debug_mode
        print(f"Starting to scrape weapons from {self.weapons_url}")
        print(f"Debug mode: {'ON' if debug_mode else 'OFF'}")
        
        try:
            soup = self.get_page(self.weapons_url)
            print("Successfully loaded the weapons page")
            
            # Find the main content area
            main_content = soup.find('div', {'class': 'mw-parser-output'})
            if not main_content:
                print("Could not find main content area")
                return
            
            # Find all weapon sections
            sections = main_content.find_all(['h2', 'h3'])
            
            current_category = None
            skip_until_next_main = False
            
            for section in sections:
                section_text = section.get_text().strip()
                print(f"\nFound section: {section_text}")
                
                # Check if this is a main category (h2) or subcategory (h3)
                is_main_category = section.name == 'h2'
                
                if is_main_category:
                    skip_until_next_main = False
                    # Determine the weapon type from the section header
                    if "Melee weapons" in section_text:
                        current_category = "melee"
                    elif "Range weapons" in section_text:
                        current_category = "range"
                    elif "Magic weapons" in section_text:
                        current_category = "magic"
                    elif "Summon weapons" in section_text:
                        current_category = "summon"
                    else:
                        current_category = None
                        skip_until_next_main = True
                    
                    if current_category:
                        print(f"\nProcessing main category: {current_category}")
                
                # Only process subcategories if we have a valid main category
                elif current_category and not skip_until_next_main:
                    print(f"Processing subcategory: {section_text}")
                    # Get the list that follows this subcategory header
                    current_element = section.find_next()
                    while current_element and current_element.name not in ['h2', 'h3']:
                        if current_element.name == 'ul':
                            # Process weapon links in this list
                            for link in current_element.find_all('a'):
                                href = link.get('href')
                                if href and not href.startswith('#'):
                                    # Construct proper URL
                                    if href.startswith('/'):
                                        weapon_url = self.base_url + href
                                    elif href.startswith('http'):
                                        weapon_url = href
                                    else:
                                        weapon_url = f"{self.base_url}/{href}"
                                    
                                    # Skip if we've already scraped this URL
                                    if weapon_url in self.scraped_urls:
                                        print(f"  Skipping already scraped weapon: {weapon_url}")
                                        continue
                                        
                                    print(f"  Scraping weapon: {weapon_url}")
                                    weapon_data = self.scrape_weapon_page(weapon_url, current_category)
                                    if weapon_data['name']:
                                        self.items_data[current_category][weapon_data['name']] = weapon_data
                                        self.scraped_urls.add(weapon_url)
                                        if self.debug_mode:
                                            print("Debug mode: Stopping after first weapon")
                                            return  # Stop after first weapon in debug mode
                        
                        current_element = current_element.find_next()
                    
        except Exception as e:
            print(f"Error in scrape_weapons: {str(e)}")
            print("Full error:")
            import traceback
            traceback.print_exc()
    
    def save_to_json(self, filename: str = 'core_keeper_weapons.json'):
        """Save scraped data to JSON file"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.items_data, f, indent=2)

if __name__ == "__main__":
    scraper = CoreKeeperScraper()
    scraper.scrape_weapons(debug_mode=False)
    scraper.save_to_json() 