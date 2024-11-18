import requests
from bs4 import BeautifulSoup
import json
import time
from typing import Dict, List

class CoreKeeperToolScraper:
    def __init__(self):
        self.base_url = "https://core-keeper.fandom.com"
        self.tools_url = f"{self.base_url}/wiki/Tools"
        self.items_data = {
            "pickaxes": {},
            "sledge_hammers": {},
            "hand_drills": {},
            "shovels": {},
            "fishing_rods": {},
            "hoes": {},
            "watering_cans": {},
            "paint_brushes": {},
            "miscellaneous": {}
        }
        self.scraped_urls = set()
        self.debug_mode = False
        
    def get_page(self, url: str) -> BeautifulSoup:
        time.sleep(1)  # Add delay to be nice to the wiki
        response = requests.get(url)
        return BeautifulSoup(response.content, 'html.parser')
    
    def scrape_tool_page(self, tool_url: str, tool_type: str) -> Dict:
        soup = self.get_page(tool_url)
        
        tool_data = {
            'name': '',
            'type': tool_type,
            'rarity': '',
            'durability': '',
            'tooltip': '',
            'category': [],
            'min_level': None,
            'max_level': None,
            'levels': {},  # Will store data for each level
            'url': tool_url
        }
        
        try:
            # Get tool name
            tool_data['name'] = soup.find('h1', {'id': 'firstHeading'}).text.strip()
            print(f"\nProcessing tool: {tool_data['name']}")
            
            # Find the infobox
            infobox = soup.find('aside', {'class': 'portable-infobox'})
            if infobox:
                # Get all data items from the infobox
                data_items = infobox.find_all('div', {'class': 'pi-item pi-data pi-item-spacing pi-border-color'})
                single_level_data = {}
                
                # First pass - get basic info and level
                for item in data_items:
                    label = item.find('h3', {'class': 'pi-data-label pi-secondary-font'})
                    value = item.find('div', {'class': 'pi-data-value pi-font'})
                    
                    if label and value:
                        key = label.text.strip().lower()
                        val = value.text.strip()
                        
                        if key == 'level':
                            level_num = ''.join(filter(str.isdigit, val))
                            if level_num:
                                tool_data['min_level'] = int(level_num)
                                tool_data['max_level'] = int(level_num)
                                single_level_data['level'] = level_num
                        elif key == 'type':
                            single_level_data['type'] = val
                        elif key == 'rarity':
                            tool_data['rarity'] = val
                            single_level_data['rarity'] = val
                        elif key == 'durability':
                            tool_data['durability'] = val
                            single_level_data['durability'] = val
                        elif key == 'tooltip':
                            tool_data['tooltip'] = val
                        elif key == 'category':
                            tool_data['category'] = [cat.strip() for cat in val.split(',')]
                        elif key == 'melee damage':
                            single_level_data['melee damage'] = val
                        elif key == 'attack rate':
                            single_level_data['attack rate'] = val.replace(' per second', '')
                        elif key == 'effects':
                            single_level_data['effects'] = val
                        elif key == 'mining damage':
                            single_level_data['mining damage'] = val.replace(' per hit', '')
                        elif key == 'fishing power':
                            single_level_data['fishing power'] = val.replace(' power', '')
                
                # If we found a level, store all the collected data
                if tool_data['min_level'] is not None:
                    level_num = str(tool_data['min_level'])
                    tool_data['levels'][level_num] = single_level_data
                    print(f"Processed single level {level_num} data")
                    print(f"Single level data: {single_level_data}")
                else:
                    # Check for multi-level data in tabs
                    tabs_list = infobox.find('ul', {'class': 'wds-tabs'})
                    if tabs_list:
                        # ... existing multi-level handling code ...
                        pass
                    else:
                        print(f"No level data found for {tool_data['name']}")

        except Exception as e:
            print(f"Error scraping {tool_url}: {str(e)}")
            import traceback
            traceback.print_exc()
            
        return tool_data
    
    def scrape_tools(self, debug_mode=False):
        """
        Scrape all tools from the tools page
        Args:
            debug_mode (bool): If True, only scrape the Stormbringer for debugging
        """
        self.debug_mode = debug_mode
        print(f"Starting to scrape tools from {self.tools_url}")
        print(f"Debug mode: {'ON' if debug_mode else 'OFF'}")
        
        try:
            if debug_mode:
                # When in debug mode, just scrape the Stormbringer directly
                stormbringer_url = f"{self.base_url}/wiki/Stormbringer"
                print(f"Debug mode: Scraping only Stormbringer at {stormbringer_url}")
                tool_data = self.scrape_tool_page(stormbringer_url, "hand_drills")
                if tool_data['name']:
                    self.items_data["hand_drills"][tool_data['name']] = tool_data
                return

            # Rest of the normal scraping logic...
            soup = self.get_page(self.tools_url)
            print("Successfully loaded the tools page")
            
            # Find the main content area
            main_content = soup.find('div', {'class': 'mw-parser-output'})
            if not main_content:
                print("Could not find main content area")
                return
            
            # Find all tool sections
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
                    if "Digging tools" in section_text:
                        current_category = None  # Will be set by subcategories
                    elif "Other tools" in section_text:
                        current_category = None  # Will be set by subcategories
                    else:
                        current_category = None
                        skip_until_next_main = True
                
                # Process subcategories
                elif not skip_until_next_main:
                    subcategory = section_text.lower().replace('[', '').replace(']', '')
                    if "pickaxes" in subcategory:
                        current_category = "pickaxes"
                    elif "sledge hammers" in subcategory:
                        current_category = "sledge_hammers"
                    elif "hand drills" in subcategory:
                        current_category = "hand_drills"
                    elif "shovels" in subcategory:
                        current_category = "shovels"
                    elif "fishing rods" in subcategory:
                        current_category = "fishing_rods"
                    elif "hoes" in subcategory:
                        current_category = "hoes"
                    elif "watering cans" in subcategory:
                        current_category = "watering_cans"
                    elif "paint brushes" in subcategory:
                        current_category = "paint_brushes"
                    elif "miscellaneous" in subcategory:
                        current_category = "miscellaneous"
                    
                    if current_category:
                        print(f"Processing subcategory: {current_category}")
                        # Get the list that follows this subcategory header
                        current_element = section.find_next()
                        while current_element and current_element.name not in ['h2', 'h3']:
                            if current_element.name == 'ul':
                                # Process tool links in this list
                                for link in current_element.find_all('a'):
                                    href = link.get('href')
                                    if href and not href.startswith('#'):
                                        # Construct proper URL
                                        if href.startswith('/'):
                                            tool_url = self.base_url + href
                                        elif href.startswith('http'):
                                            tool_url = href
                                        else:
                                            tool_url = f"{self.base_url}/{href}"
                                        
                                        # Skip if we've already scraped this URL
                                        if tool_url in self.scraped_urls:
                                            print(f"  Skipping already scraped tool: {tool_url}")
                                            continue
                                            
                                        print(f"  Scraping tool: {tool_url}")
                                        tool_data = self.scrape_tool_page(tool_url, current_category)
                                        if tool_data['name']:
                                            self.items_data[current_category][tool_data['name']] = tool_data
                                            self.scraped_urls.add(tool_url)
                                            if self.debug_mode:
                                                print("Debug mode: Stopping after first tool")
                                                return  # Stop after first tool in debug mode
                            
                            current_element = current_element.find_next()
                    
        except Exception as e:
            print(f"Error in scrape_tools: {str(e)}")
            print("Full error:")
            import traceback
            traceback.print_exc()
    
    def save_to_json(self, filename: str = 'core_keeper_tools.json'):
        """Save scraped data to JSON file"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.items_data, f, indent=2)

if __name__ == "__main__":
    scraper = CoreKeeperToolScraper()
    scraper.scrape_tools(debug_mode=False)
    scraper.save_to_json() 