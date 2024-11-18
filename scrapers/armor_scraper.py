import requests
from bs4 import BeautifulSoup
import json
import time
from typing import Dict, List
import os

class CoreKeeperArmorScraper:
    def __init__(self):
        self.base_url = "https://core-keeper.fandom.com"
        self.armor_url = f"{self.base_url}/wiki/Armor"
        self.items_data = {
            "armor_sets": {},
            "miscellaneous": {}  # For armor pieces that don't belong to sets
        }
        self.scraped_urls = set()
        self.debug_mode = False
    
    def get_page(self, url: str) -> BeautifulSoup:
        time.sleep(1)  # Add delay to be nice to the wiki
        response = requests.get(url)
        return BeautifulSoup(response.content, 'html.parser')
    
    def scrape_armor_piece(self, armor_url: str) -> Dict:
        """Scrape individual armor piece data"""
        soup = self.get_page(armor_url)
        armor_data = {
            'name': '',
            'slot': '',  # helm, chest, pants
            'category': [],
            'min_level': None,
            'max_level': None,
            'levels': {},  # Will store data for each level
            'url': armor_url,
            'set_bonus': {
                'required_pieces': [],
                'bonuses': {}
            }
        }
        
        try:
            # Get armor piece name
            armor_data['name'] = soup.find('h1', {'id': 'firstHeading'}).text.strip()
            print(f"\nProcessing armor piece: {armor_data['name']}")
            
            # Find the infobox
            infobox = soup.find('aside', {'class': 'portable-infobox'})
            if infobox:
                # Process basic info
                for label in infobox.find_all('div', {'class': 'pi-item'}):
                    label_name = label.find('div', {'class': 'pi-data-label'})
                    label_value = label.find('div', {'class': 'pi-data-value'})
                    if label_name and label_value:
                        key = label_name.text.strip().lower()
                        value = label_value.text.strip()
                        if key == 'category':
                            armor_data['category'] = [cat.strip() for cat in value.split(',')]
                        elif key == 'slot':
                            armor_data['slot'] = value.lower()
                
                # Find set bonus information
                set_sections = infobox.find_all('section', {'class': 'pi-item'})
                for section in set_sections:
                    header = section.find('h2', {'class': 'pi-header'})
                    if header and 'set bonus' in header.text.strip().lower():
                        bonus_div = section.find('div', {'class': 'pi-data-value pi-font'})
                        if bonus_div:
                            # Get all set bonus effects
                            bonus_texts = bonus_div.find_all('div', recursive=False)
                            for bonus_text_div in bonus_texts:
                                bonus_text = bonus_text_div.text.strip()
                                if 'set:' in bonus_text.lower():
                                    parts = bonus_text.lower().split('set:', 1)
                                    set_size = ''.join(filter(str.isdigit, parts[0]))
                                    effect = parts[1].strip()
                                    if set_size:
                                        # Initialize list for this set size if it doesn't exist
                                        if set_size not in armor_data['set_bonus']['bonuses']:
                                            armor_data['set_bonus']['bonuses'][set_size] = []
                                        # Add this bonus to the list
                                        armor_data['set_bonus']['bonuses'][set_size].append(effect)
                
                # Process level data
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
                    armor_data['min_level'] = min(available_levels)
                    armor_data['max_level'] = max(available_levels)
                    
                    # Process each level's data
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
                            armor_data['levels'][level_num] = level_data
                
        except Exception as e:
            print(f"Error scraping {armor_url}: {str(e)}")
            
        return armor_data
    
    def scrape_armor_set(self, set_url: str) -> Dict:
        """Scrape an armor set page to get overall set info and piece links"""
        soup = self.get_page(set_url)
        set_data = {
            'name': '',
            'pieces': {},
            'set_bonus': {
                'bonuses': {}  # Will store lists of bonuses for each set size
            }
        }
        
        try:
            # Get set name
            set_data['name'] = soup.find('h1', {'id': 'firstHeading'}).text.strip()
            print(f"\nProcessing armor set: {set_data['name']}")
            
            # Find the infobox-list div that contains the individual pieces
            infobox_list = soup.find('div', {'class': 'infobox-list'})
            if infobox_list:
                # Find all armor piece infoboxes within this div
                piece_infoboxes = infobox_list.find_all('aside', {'class': 'portable-infobox'})
                print(f"Found {len(piece_infoboxes)} armor pieces")
                for infobox in piece_infoboxes:
                    piece_data = self.scrape_armor_piece_from_infobox(infobox)
                    if piece_data['name']:
                        set_data['pieces'][piece_data['name']] = piece_data
                        print(f"Added piece: {piece_data['name']}")
            else:
                print("Could not find infobox-list div")
                
            # Process set bonus from the first (main) infobox on the page
            main_infobox = soup.find('aside', {'class': 'portable-infobox'})
            if main_infobox:
                set_sections = main_infobox.find_all('section', {'class': 'pi-item'})
                for section in set_sections:
                    header = section.find('h2', {'class': 'pi-header'})
                    if header and 'set bonus' in header.text.strip().lower():
                        bonus_div = section.find('div', {'class': 'pi-data-value pi-font'})
                        if bonus_div:
                            # Get all set bonus effects
                            bonus_texts = bonus_div.find_all('div', recursive=False)
                            for bonus_text_div in bonus_texts:
                                bonus_text = bonus_text_div.text.strip()
                                if 'set:' in bonus_text.lower():
                                    parts = bonus_text.lower().split('set:', 1)
                                    set_size = ''.join(filter(str.isdigit, parts[0]))
                                    effect = parts[1].strip()
                                    if set_size:
                                        # Initialize list for this set size if it doesn't exist
                                        if set_size not in set_data['set_bonus']['bonuses']:
                                            set_data['set_bonus']['bonuses'][set_size] = []
                                        # Add this bonus to the list
                                        set_data['set_bonus']['bonuses'][set_size].append(effect)
                    
        except Exception as e:
            print(f"Error scraping set {set_url}: {str(e)}")
            import traceback
            traceback.print_exc()
            
        return set_data
    
    def scrape_armor_piece_from_infobox(self, infobox) -> Dict:
        """Scrape armor piece data from its infobox"""
        piece_data = {
            'name': '',
            'slot': '',
            'rarity': '',
            'durability': '',
            'tooltip': '',
            'category': [],
            'min_level': None,
            'max_level': None,
            'levels': {},  # Will store data for each level including effects
        }
        
        try:
            # Get the name from the title element
            title = infobox.find('h2', {'class': 'pi-title'})
            if title:
                piece_data['name'] = title.text.strip()
                print(f"Processing armor piece: {piece_data['name']}")
            
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
                piece_data['min_level'] = min(available_levels)
                piece_data['max_level'] = max(available_levels)
                print(f"Found levels from {piece_data['min_level']} to {piece_data['max_level']}")
                
                # Find all tab content sections
                tab_contents = infobox.find_all('div', {'class': 'wds-tab__content'})
                for content in tab_contents:
                    level_data = {}
                    
                    # Find all pi-item pi-data divs directly
                    data_items = content.find_all('div', {'class': 'pi-item pi-data pi-item-spacing pi-border-color'})
                    for item in data_items:
                        label = item.find('h3', {'class': 'pi-data-label pi-secondary-font'})
                        value = item.find('div', {'class': 'pi-data-value pi-font'})
                        
                        if label and value:
                            key = label.text.strip().lower()
                            val = value.text.strip()
                            
                            # Store basic info in the piece_data if we're on level 1
                            if key in ['rarity', 'slot', 'durability', 'tooltip']:
                                if 'level' in level_data and level_data['level'] == '1':
                                    piece_data[key] = val
                            elif key == 'category':
                                if 'level' in level_data and level_data['level'] == '1':
                                    piece_data['category'] = [cat.strip() for cat in val.split(',')]
                            elif key == 'effects':
                                # Keep the full effects text including upgrade notes
                                level_data[key] = value.text.strip()
                            else:
                                # Clean up other values (remove upgrade notes in parentheses)
                                if '(' in val:
                                    val = val.split('(')[0].strip()
                                level_data[key] = val
                    
                    # Only add the level data if we found a level number
                    if 'level' in level_data:
                        level_num = level_data['level']
                        piece_data['levels'][level_num] = level_data
                        print(f"Processed level {level_num} data")
            
            else:
                print(f"No level data found for {piece_data['name']}")
                
                # If no levels found, try to get basic info directly
                for label in infobox.find_all('div', {'class': 'pi-item'}):
                    label_name = label.find('div', {'class': 'pi-data-label'})
                    label_value = label.find('div', {'class': 'pi-data-value'})
                    if label_name and label_value:
                        key = label_name.text.strip().lower()
                        value = label_value.text.strip()
                        
                        if key in ['rarity', 'slot', 'durability', 'tooltip']:
                            piece_data[key] = value
                        elif key == 'category':
                            piece_data['category'] = [cat.strip() for cat in value.split(',')]

        except Exception as e:
            print(f"Error scraping armor piece from infobox: {str(e)}")
            import traceback
            traceback.print_exc()
            
        return piece_data
    
    def scrape_armor_sets(self, debug_mode=False):
        self.debug_mode = debug_mode
        print(f"Starting to scrape armor from {self.armor_url}")
        print(f"Debug mode: {'ON' if debug_mode else 'OFF'}")
        
        try:
            soup = self.get_page(self.armor_url)
            print("Successfully loaded the armor page")
            
            # Find all tables
            tables = soup.find_all('table', {'class': 'fandom-table'})
            print(f"Found {len(tables)} tables")
            
            for table in tables:
                # Find the section header
                header = table.find_previous(['h2', 'h3'])
                if not header:
                    continue
                
                section_text = header.get_text().strip().lower()
                print(f"\nProcessing section: {section_text}")
                
                # Determine if this is the miscellaneous table
                is_misc_table = 'miscellaneous' in section_text
                
                # Process each row in the table
                for row in table.find_all('tr'):
                    cells = row.find_all('td')
                    if not cells or len(cells) < 2:
                        continue
                    
                    # Always look at the second column, regardless of table type
                    set_cell = cells[1]
                    links = set_cell.find_all('a', href=True)
                    for link in links:
                        href = link.get('href')
                        if href and not href.startswith('#'):
                            if href.startswith('/'):
                                armor_url = self.base_url + href
                            else:
                                armor_url = f"{self.base_url}/{href}"
                            
                            if armor_url in self.scraped_urls:
                                print(f"  Skipping already scraped armor: {armor_url}")
                                continue
                            
                            if is_misc_table:
                                print(f"  Scraping misc armor piece: {armor_url}")
                                armor_data = self.scrape_armor_piece(armor_url)
                                if armor_data['name']:
                                    self.items_data["miscellaneous"][armor_data['name']] = armor_data
                                    self.scraped_urls.add(armor_url)
                            else:
                                print(f"  Scraping armor set: {armor_url}")
                                set_data = self.scrape_armor_set(armor_url)
                                if set_data['name']:
                                    self.items_data["armor_sets"][set_data['name']] = set_data
                                    self.scraped_urls.add(armor_url)
                            
                            if self.debug_mode:
                                return
            
                # Stop processing after the miscellaneous table
                if is_misc_table:
                    print("Finished processing miscellaneous table. Stopping scraper.")
                    break
            
        except Exception as e:
            print(f"Error in scrape_armor_sets: {str(e)}")
            print("Full error:")
            import traceback
            traceback.print_exc()
    
    def save_to_json(self, filename: str = 'core_keeper_armor.json'):
        """Save scraped data to JSON file"""
        # Create scraped_json directory if it doesn't exist
        os.makedirs('../scraped_json', exist_ok=True)
        
        # Save to the scraped_json directory
        filepath = os.path.join('../scraped_json', filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.items_data, f, indent=2)

if __name__ == "__main__":
    scraper = CoreKeeperArmorScraper()
    scraper.scrape_armor_sets(debug_mode=False)
    scraper.save_to_json() 