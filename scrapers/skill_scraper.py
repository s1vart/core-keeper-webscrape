import requests
from bs4 import BeautifulSoup
import json
import time
import re
from typing import Dict, List, Tuple

class CoreKeeperSkillScraper:
    def __init__(self):
        self.base_url = "https://core-keeper.fandom.com"
        self.skills_url = f"{self.base_url}/wiki/Skills"
        self.items_data = {}
        
    def get_page(self, url: str) -> BeautifulSoup:
        """Get and parse a webpage"""
        time.sleep(1)  # Be nice to the wiki
        response = requests.get(url)
        return BeautifulSoup(response.content, 'html.parser')
    
    def parse_effect_range(self, effect: str) -> Tuple[float, float, str]:
        """
        Parse the effect range and return start value, end value, and the effect text
        Example: "+2-10% mining damage" -> (2, 10, "% mining damage")
        """
        # Find the range pattern (e.g., "2-10", "0.2-1", "10-50")
        range_match = re.search(r'([0-9.]+)[-–]([0-9.]+)', effect)
        if not range_match:
            return None, None, effect
            
        start_val = float(range_match.group(1))
        end_val = float(range_match.group(2))
        
        # Get the text before and after the range
        prefix = effect[:range_match.start()].strip()
        suffix = effect[range_match.end():].strip()
        
        # Combine prefix and suffix, keeping any +/- from prefix
        effect_text = prefix.replace('+', '').replace('-', '') + suffix
        
        return start_val, end_val, effect_text
    
    def calculate_level_effects(self, start_val: float, end_val: float, effect_text: str) -> Dict[str, str]:
        """Calculate effects for levels 1-5 based on start and end values"""
        level_effects = {}
        if start_val is None or end_val is None:
            return level_effects
            
        # Calculate increment per level
        increment = (end_val - start_val) / 4  # 4 steps for 5 levels
        
        for level in range(1, 6):
            value = start_val + (level - 1) * increment
            # Format value to match original precision
            if value.is_integer():
                formatted_value = str(int(value))
            else:
                formatted_value = f"{value:.1f}"
            
            # Add + sign if the original effect had one
            if effect_text.startswith('%'):
                level_effects[str(level)] = f"+{formatted_value}{effect_text}"
            else:
                level_effects[str(level)] = f"{formatted_value} {effect_text}"
                
        return level_effects
    
    def scrape_skills(self):
        """Scrape all skills from the skills page"""
        print(f"Starting to scrape skills from {self.skills_url}")
        
        try:
            soup = self.get_page(self.skills_url)
            
            # Find the Skills section
            skills_section = None
            for h2 in soup.find_all('h2'):
                if 'Skills' in h2.get_text():
                    skills_section = h2
                    break
            
            if not skills_section:
                print("Could not find Skills section")
                return
            
            current_category = None
            
            # Process each element after the Skills section
            current_element = skills_section.find_next()
            while current_element and not (current_element.name == 'h2' and 'Achievements' in current_element.get_text()):
                # Check for category headers (h3)
                if current_element.name == 'h3':
                    current_category = current_element.get_text().strip().replace('[', '').replace(']', '')
                    print(f"\nProcessing category: {current_category}")
                    self.items_data[current_category] = {'skills': {}}
                
                # Check for skill tables
                elif current_element.name == 'table' and current_category:
                    # Process each row in the table
                    for row in current_element.find_all('tr'):
                        cells = row.find_all(['th', 'td'])
                        if len(cells) >= 3:  # We need at least name, effect, and tier
                            skill_name = cells[0].get_text().strip()
                            effect = cells[1].get_text().strip()
                            tier = cells[2].get_text().strip()
                            
                            if skill_name and not skill_name.startswith('Talent'):  # Skip header row
                                print(f"Processing skill: {skill_name}")
                                
                                # Parse the effect range and calculate level effects
                                start_val, end_val, effect_text = self.parse_effect_range(effect)
                                level_effects = self.calculate_level_effects(start_val, end_val, effect_text)
                                
                                # Store the skill data
                                self.items_data[current_category]['skills'][skill_name] = {
                                    'name': skill_name,
                                    'base_effect': effect,
                                    'tier': tier,
                                    'levels': level_effects
                                }
                
                current_element = current_element.find_next()
            
        except Exception as e:
            print(f"Error in scrape_skills: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def save_to_json(self, filename: str = 'core_keeper_skills.json'):
        """Save scraped data to JSON file"""
        import os
        
        # Create scraped_json directory if it doesn't exist
        os.makedirs('../scraped_json', exist_ok=True)
        
        # Save to the scraped_json directory
        filepath = os.path.join('../scraped_json', filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.items_data, f, indent=2)

if __name__ == "__main__":
    scraper = CoreKeeperSkillScraper()
    scraper.scrape_skills()
    scraper.save_to_json() 