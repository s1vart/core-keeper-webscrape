from flask import Flask, render_template, jsonify, request
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum
import json
import os
from datetime import datetime, timedelta
from flask_sqlalchemy import SQLAlchemy
import logging
from logging.handlers import RotatingFileHandler
from models import Weapon, WeaponStats, db, Build
import re
from functools import lru_cache

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///core_keeper.db'
db.init_app(app)

class ItemType(Enum):
    WEAPON = "weapon"
    ARMOR = "armor"
    FOOD = "food"
    POTION = "potion"
    ACCESSORY = "accessory"

@dataclass
class Item:
    name: str
    type: ItemType
    stats: Dict[str, float]
    description: str
    buffs: List[str] = field(default_factory=list)
    debuffs: List[str] = field(default_factory=list)
    duration: Optional[int] = None

    def __post_init__(self):
        # Convert string type to enum if needed
        if isinstance(self.type, str):
            self.type = ItemType(self.type)

@dataclass
class Skill:
    name: str
    tree: str  # e.g., "Combat", "Exploration", "Crafting"
    level: int
    stats: Dict[str, float]
    description: str

@dataclass
class Build:
    name: str
    weapon: Optional[Item]
    armor_pieces: List[Item]  # Head, Chest, Legs, etc.
    food_buffs: List[Item]    # Active food buffs
    potion_buffs: List[Item]  # Active potion buffs
    skills: List[Skill]
    description: str
    accessory: Optional[Item] = None

    def calculate_dps(self) -> Dict[str, float]:
        base_stats = {
            "damage": 0.0,
            "damage_low": 0.0,
            "damage_high": 0.0,
            "attack_speed": 1.0,
            "crit_chance": 0.0,
            "crit_multiplier": 1.5,
            "damage_multiplier": 1.0,
            "armor": 0.0,
            "health": 100.0,
        }
        
        # Keep track of non-numeric stats
        text_stats = {
            "rarity": "",
            "effects": [],
            "buffs": [],
            "debuffs": []
        }
        
        # Add weapon stats
        if self.weapon:
            for stat, value in self.weapon.stats.items():
                try:
                    # Only try to convert numeric stats
                    if stat not in ['rarity', 'effects', 'buffs', 'debuffs']:
                        if isinstance(value, str):
                            value = float(value)
                        base_stats[stat] = base_stats.get(stat, 0.0) + value
                    else:
                        # Store non-numeric stats separately
                        text_stats[stat] = value
                except (ValueError, TypeError) as e:
                    app.logger.error(f"Error converting stat {stat} with value {value}: {str(e)}")
                    continue

        # Add accessory stats and effects
        if self.accessory:
            if isinstance(self.accessory, dict):  # If accessory is passed as a dictionary
                effects = self.accessory.get('effects', [])
                if isinstance(effects, str):
                    text_stats['effects'].extend(effects.split('+'))
            else:  # If accessory is an Item object
                text_stats['effects'].extend(self.accessory.buffs)
                text_stats['effects'].extend(self.accessory.debuffs)

        # Calculate DPS using average damage
        avg_damage = (base_stats['damage_high'] + base_stats['damage_low']) / 2 if 'damage_high' in base_stats else base_stats['damage']
        base_damage = avg_damage * base_stats['damage_multiplier']
        crit_dps = base_damage * base_stats['crit_multiplier'] * base_stats['crit_chance']
        normal_dps = base_damage * (1 - base_stats['crit_chance'])
        total_dps = (crit_dps + normal_dps) * base_stats['attack_speed']

        return {
            'base_stats': base_stats,
            'text_stats': text_stats,  # Include non-numeric stats in the response
            'total_dps': total_dps,
            'effective_damage_per_hit': base_damage,
            'attacks_per_second': base_stats['attack_speed']
        }

ITEMS_DB = []

@lru_cache(maxsize=32)
def load_game_data():
    """Load and cache game data"""
    try:
        with open('scraped_json/core_keeper_weapons.json', 'r', encoding='utf-8') as f:
            weapons_data = json.load(f)
        with open('scraped_json/core_keeper_accessories.json', 'r', encoding='utf-8') as f:
            accessories_data = json.load(f)
        return weapons_data, accessories_data
    except Exception as e:
        app.logger.error(f"Error loading game data: {e}")
        raise

# Add this function after load_game_data()
def load_accessories_data():
    """
    Loads accessories data from local JSON file
    """
    try:
        with open('scraped_json/core_keeper_accessories.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            accessories = []
            
            for acc_name, acc_data in data.items():
                try:
                    item = {
                        'name': acc_name,
                        'type': 'accessory',
                        'stats': acc_data.get('stats', {}),
                        'buffs': acc_data.get('buffs', []),
                        'debuffs': acc_data.get('debuffs', []),
                        'description': acc_data.get('description', ''),
                        'effects': acc_data.get('effects', '')
                    }
                    accessories.append(item)
                    app.logger.info(f"Added accessory: {acc_name}")
                except Exception as e:
                    app.logger.error(f"Error processing accessory {acc_name}: {str(e)}")
                    
            return accessories
    except Exception as e:
        app.logger.error(f"Error loading core_keeper_accessories.json: {str(e)}")
        app.logger.exception(e)
        return []

# Add these constants
DATA_FILE = "game_data.json"
DATA_REFRESH_INTERVAL = timedelta(days=1)  # Update data daily

def initialize_data():
    global ITEMS_DB
    ITEMS_DB = []
    game_data = load_game_data()
    accessories_data = load_accessories_data()
    
    app.logger.info(f"Loaded game data with {len(game_data)} items and {len(accessories_data)} accessories")
    
    try:
        # Convert weapons data to Item objects
        for item_data in game_data:
            try:
                item_type = item_data['type']
                if isinstance(item_type, str):
                    item_type = ItemType(item_type.lower())
                
                ITEMS_DB.append(Item(
                    name=item_data['name'],
                    type=item_type,
                    stats=item_data['stats'],
                    description=item_data.get('description', '')
                ))
            except Exception as e:
                app.logger.error(f"Error adding item {item_data}: {str(e)}")
                
        # Convert accessories data to Item objects
        for acc_data in accessories_data:
            try:
                ITEMS_DB.append(Item(
                    name=acc_data['name'],
                    type=ItemType.ACCESSORY,  # Add ACCESSORY to ItemType enum
                    stats=acc_data['stats'],
                    description=acc_data.get('description', ''),
                    buffs=acc_data.get('buffs', []),
                    debuffs=acc_data.get('debuffs', [])
                ))
            except Exception as e:
                app.logger.error(f"Error adding accessory {acc_data}: {str(e)}")
                
    except Exception as e:
        app.logger.error(f"Error initializing data: {str(e)}")

    app.logger.info(f"Initialized {len(ITEMS_DB)} total items")

SKILLS_DB = [
    Skill(
        name="Sword Mastery",
        tree="Combat",
        level=1,
        stats={"damage_multiplier": 1.1},
        description="Increases sword damage by 10%"
    ),
    # Add more skills here
]

# Add this helper function
def set_nav_active(active_page):
    return {
        'calculator': active_page == 'calculator',
        'builds': active_page == 'builds',
        'compare': active_page == 'compare',
        'stats': active_page == 'stats',
        'guide': active_page == 'guide'
    }

@app.route('/')
def home():
    try:
        if not ITEMS_DB:
            initialize_data()
        return render_template('index.html', nav=set_nav_active('calculator'))
    except Exception as e:
        app.logger.error(f'Error in home route: {str(e)}')
        return f"An error occurred: {str(e)}", 500

@app.route('/api/items')
def get_items():
    try:
        with open('scraped_json/core_keeper_weapons.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        items_list = []
        
        # Process melee weapons
        for weapon_name, weapon_data in data.get('melee', {}).items():
            if not weapon_data.get('levels'):
                continue
                
            # Get first level data
            first_level = next(iter(weapon_data['levels'].values()))
            
            # Create item entry
            item = {
                'name': weapon_name,
                'type': 'weapon',
                'stats': {
                    'damage': first_level.get('damage', '0-0'),
                    'attack_speed': float(first_level.get('attack rate', 1.0)),
                    'durability': first_level.get('durability', 100)
                },
                'description': first_level.get('tooltip', '')
            }
            items_list.append(item)
            
        # Process ranged weapons
        for weapon_name, weapon_data in data.get('range', {}).items():
            if not weapon_data.get('levels'):
                continue
                
            first_level = next(iter(weapon_data['levels'].values()))
            item = {
                'name': weapon_name,
                'type': 'weapon',
                'stats': {
                    'damage': first_level.get('damage', '0-0'),
                    'attack_speed': float(first_level.get('attack rate', 1.0)),
                    'durability': first_level.get('durability', 100)
                },
                'description': first_level.get('tooltip', '')
            }
            items_list.append(item)
            
        # Process magic weapons
        for weapon_name, weapon_data in data.get('magic', {}).items():
            if not weapon_data.get('levels'):
                continue
                
            first_level = next(iter(weapon_data['levels'].values()))
            item = {
                'name': weapon_name,
                'type': 'weapon',
                'stats': {
                    'damage': first_level.get('damage', '0-0'),
                    'attack_speed': float(first_level.get('attack rate', 1.0)),
                    'durability': first_level.get('durability', 100),
                    'mana': first_level.get('mana', 0)
                },
                'description': first_level.get('tooltip', '')
            }
            items_list.append(item)

        return jsonify(items_list)
    except Exception as e:
        app.logger.error(f"Error in get_items: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/skills')
def get_skills():
    if not ITEMS_DB:  # Initialize data if not already done
        initialize_data()
    return jsonify([vars(skill) for skill in SKILLS_DB])

@app.route('/api/builds', methods=['GET'])
def get_builds():
    try:
        builds = Build.query.order_by(Build.updated_at.desc()).all()
        return jsonify([{
            'id': build.id,
            'name': build.name,
            'description': build.description,
            'weapon_name': build.weapon_name,
            'armor_pieces': build.armor_pieces,
            'food_buffs': build.food_buffs,
            'potion_buffs': build.potion_buffs,
            'skills': build.skills,
            'total_dps': build.total_dps,
            'effective_damage': build.effective_damage,
            'attack_speed': build.attack_speed,
            'created_at': build.created_at.isoformat(),
            'updated_at': build.updated_at.isoformat()
        } for build in builds])
    except Exception as e:
        app.logger.error(f"Error getting builds: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/builds/<int:build_id>', methods=['GET'])
def get_build(build_id):
    try:
        build = Build.query.get_or_404(build_id)
        return jsonify({
            'id': build.id,
            'name': build.name,
            'description': build.description,
            'weapon_name': build.weapon_name,
            'armor_pieces': build.armor_pieces,
            'food_buffs': build.food_buffs,
            'potion_buffs': build.potion_buffs,
            'skills': build.skills,
            'total_dps': build.total_dps,
            'effective_damage': build.effective_damage,
            'attack_speed': build.attack_speed
        })
    except Exception as e:
        app.logger.error(f"Error getting build {build_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/builds', methods=['POST'])
def save_build():
    try:
        data = request.get_json()
        
        # Calculate DPS and other stats
        stats = calculate_build_stats(data)
        
        build = Build(
            name=data['name'],
            description=data.get('description', ''),
            weapon_name=data.get('weapon_name'),
            armor_pieces=data.get('armor_pieces', []),
            food_buffs=data.get('food_buffs', []),
            potion_buffs=data.get('potion_buffs', []),
            skills=data.get('skills', []),
            total_dps=stats['total_dps'],
            effective_damage=stats['effective_damage'],
            attack_speed=stats['attack_speed']
        )
        
        db.session.add(build)
        db.session.commit()
        
        return jsonify({
            'id': build.id,
            'message': 'Build saved successfully'
        })
    except Exception as e:
        app.logger.error(f"Error saving build: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/builds/<int:build_id>', methods=['PUT'])
def update_build(build_id):
    try:
        build = Build.query.get_or_404(build_id)
        data = request.get_json()
        
        # Calculate DPS and other stats
        stats = calculate_build_stats(data)
        
        # Update build
        build.name = data['name']
        build.description = data.get('description', '')
        build.weapon_name = data.get('weapon_name')
        build.armor_pieces = data.get('armor_pieces', [])
        build.food_buffs = data.get('food_buffs', [])
        build.potion_buffs = data.get('potion_buffs', [])
        build.skills = data.get('skills', [])
        build.total_dps = stats['total_dps']
        build.effective_damage = stats['effective_damage']
        build.attack_speed = stats['attack_speed']
        
        db.session.commit()
        
        return jsonify({'message': 'Build updated successfully'})
    except Exception as e:
        app.logger.error(f"Error updating build {build_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/builds/<int:build_id>', methods=['DELETE'])
def delete_build(build_id):
    try:
        build = Build.query.get_or_404(build_id)
        db.session.delete(build)
        db.session.commit()
        return jsonify({'message': 'Build deleted successfully'})
    except Exception as e:
        app.logger.error(f"Error deleting build {build_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500

def calculate_build_stats(build_data):
    """Calculate build stats based on weapon and other equipment"""
    try:
        # Get weapon data
        weapon_name = build_data.get('weapon_name')
        weapon = Weapon.query.filter_by(name=weapon_name).first()
        
        if not weapon:
            return {
                'total_dps': 0.0,
                'effective_damage': 0.0,
                'attack_speed': 1.0
            }
            
        # Get base stats
        stats = weapon.stats
        damage_low = float(stats.get('damage_low', 0))
        damage_high = float(stats.get('damage_high', 0))
        attack_speed = float(stats.get('attack_speed', 1.0))
        crit_chance = float(stats.get('crit_chance', 0.05))
        
        # Calculate effective damage
        avg_damage = (damage_low + damage_high) / 2
        effective_damage = avg_damage * (1 + (crit_chance * 0.5))  # Assuming 50% crit damage
        
        # Calculate DPS
        total_dps = effective_damage * attack_speed
        
        return {
            'total_dps': total_dps,
            'effective_damage': effective_damage,
            'attack_speed': attack_speed
        }
        
    except Exception as e:
        app.logger.error(f"Error calculating build stats: {str(e)}")
        return {
            'total_dps': 0.0,
            'effective_damage': 0.0,
            'attack_speed': 1.0
        }

@app.route('/api/calculate-dps', methods=['POST'])
def calculate_dps():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
            
        required_fields = ['weapon', 'accessory']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify({"error": f"Missing required fields: {', '.join(missing_fields)}"}), 400

        # Load weapon data
        with open('core_keeper_weapons.json', 'r', encoding='utf-8') as f:
            weapons_data = json.load(f)
            
        # Load accessories data
        with open('core_keeper_accessories.json', 'r', encoding='utf-8') as f:
            accessories_data = json.load(f)
        
        # Get weapon stats
        weapon_name = data['weapon']['name']
        weapon_level = str(data['weapon']['level'])  # Ensure level is string
        weapon_stats = None
        
        # Search through weapon types
        for weapon_type in ['melee', 'range', 'magic']:
            if weapon_type in weapons_data and weapon_name in weapons_data[weapon_type]:
                weapon_data = weapons_data[weapon_type][weapon_name]
                if weapon_level in weapon_data.get('levels', {}):
                    weapon_stats = weapon_data['levels'][weapon_level]
                break
        
        if not weapon_stats:
            return jsonify({
                'total_dps': 0.0,
                'effective_damage_per_hit': 0.0,
                'attacks_per_second': 1.0
            })
            
        # Parse weapon stats - handle the unicode minus sign
        damage_str = weapon_stats.get('damage', '0-0').replace('\u2212', '-')
        damage_low, damage_high = map(float, damage_str.split('-'))
        attack_speed = float(weapon_stats.get('attack rate', 1.0))
        
        # Calculate base stats
        avg_damage = (damage_low + damage_high) / 2
        base_damage = avg_damage
        
        # Apply accessory effects if present
        if data['accessory']['name'] and data['accessory']['level']:
            acc_name = data['accessory']['name']
            acc_level = str(data['accessory']['level'])
            
            # Find accessory in the data
            for category, items in accessories_data.items():
                if acc_name in items:
                    acc_data = items[acc_name]
                    if 'levels' in acc_data and acc_level in acc_data['levels']:
                        level_data = acc_data['levels'][acc_level]
                        effects = level_data.get('effects', '')
                        
                        # Parse effects for damage modifiers
                        if effects:
                            # Add damage bonus effects here
                            damage_bonus_match = re.search(r'\+(\d+(?:\.\d+)?)% (?:melee|range|magic) damage', effects)
                            if damage_bonus_match:
                                damage_bonus = float(damage_bonus_match.group(1)) / 100
                                base_damage *= (1 + damage_bonus)
                            
                            # Add attack speed bonus effects here
                            speed_bonus_match = re.search(r'\+(\d+(?:\.\d+)?)% (?:melee|range|magic) attack speed', effects)
                            if speed_bonus_match:
                                speed_bonus = float(speed_bonus_match.group(1)) / 100
                                attack_speed *= (1 + speed_bonus)
        
        # Calculate final stats
        total_dps = base_damage * attack_speed
        
        return jsonify({
            'total_dps': total_dps,
            'effective_damage_per_hit': base_damage,
            'attacks_per_second': attack_speed
        })
        
    except json.JSONDecodeError:
        app.logger.error("Invalid JSON data received")
        return jsonify({"error": "Invalid JSON data"}), 400
    except Exception as e:
        app.logger.exception("Error in calculate_dps")
        return jsonify({"error": str(e)}), 500

@app.route('/stats')
def stats_page():
    if not ITEMS_DB:
        initialize_data()
    return render_template('stats.html', nav=set_nav_active('stats'))

@app.route('/api/all-stats')
def get_all_stats():
    try:
        # Load all data with updated paths
        with open('scraped_json/core_keeper_weapons.json', 'r', encoding='utf-8') as f:
            weapons_data = json.load(f)
        with open('scraped_json/core_keeper_accessories.json', 'r', encoding='utf-8') as f:
            accessories_data = json.load(f)
        with open('scraped_json/core_keeper_armor.json', 'r', encoding='utf-8') as f:
            armor_data = json.load(f)
            
        formatted_data = {
            'weapons': {},
            'accessories': {},
            'armor': {}
        }
        
        # Process weapons
        for weapon_type in ['melee', 'range', 'magic']:
            if weapon_type in weapons_data:
                for weapon_name, weapon_data in weapons_data[weapon_type].items():
                    if weapon_data.get('levels'):
                        processed_levels = {}
                        for level, level_data in weapon_data['levels'].items():
                            processed_level = dict(level_data)
                            
                            # Process weapon effects
                            effects_list = []
                            
                            # Handle main stats as effects
                            if 'damage' in level_data:
                                effects_list.append(f"Damage: {level_data['damage']}")
                            if 'attack rate' in level_data:
                                effects_list.append(f"Attack Rate: {level_data['attack rate']}")
                            
                            # Handle additional effects (like burn damage)
                            if 'effects' in level_data:
                                effects_list.append(level_data['effects'])
                            
                            # Handle secondary effects
                            if 'secondary' in level_data:
                                effects_list.append(f"Secondary: {level_data['secondary']}")
                                
                            processed_level['effects'] = effects_list
                            processed_levels[level] = processed_level
                            
                        formatted_data['weapons'][weapon_name] = {
                            'type': weapon_type,
                            'levels': processed_levels
                        }
                    
        # Process accessories
        for category, items in accessories_data.items():
            for item_name, item_data in items.items():
                if item_data.get('levels'):
                    processed_levels = {}
                    for level, level_data in item_data['levels'].items():
                        processed_level = dict(level_data)
                        
                        # Process effects
                        if 'effects' in level_data:
                            effects = level_data['effects']
                            if isinstance(effects, str):
                                effects_list = effects.split('+')
                                effects_list = [e.strip() for e in effects_list if e.strip()]
                                effects_list = [f"+{e}" for e in effects_list]
                                processed_level['effects'] = effects_list
                            
                        processed_levels[level] = processed_level
                        
                    formatted_data['accessories'][item_name] = {
                        'type': category,
                        'levels': processed_levels,
                        'min_level': item_data.get('min_level'),
                        'max_level': item_data.get('max_level')
                    }
        
        # Process armor - Updated to handle the nested structure and empty slots
        if 'armor_sets' in armor_data:
            for set_name, set_data in armor_data['armor_sets'].items():
                if 'pieces' in set_data:
                    for piece_name, piece_data in set_data['pieces'].items():
                        if piece_data.get('levels'):
                            processed_levels = {}
                            for level, level_data in piece_data['levels'].items():
                                processed_level = dict(level_data)
                                
                                # Process armor effects
                                if 'effects' in level_data:
                                    effects = level_data['effects']
                                    print(f"\nRaw effects for {piece_name} level {level}: {effects}")
                                    
                                    if isinstance(effects, str):
                                        effects_list = []
                                        # Split by plus signs
                                        raw_effects = [e for e in effects.split('+') if e.strip()]
                                        
                                        for effect in raw_effects:
                                            print(f"Original effect: '{effect}'")
                                            # Remove parenthetical content using regex
                                            main_effect = re.sub(r'\s*\([^)]*\)', '', effect).strip()
                                            print(f"Effect after removing parentheses: '{main_effect}'")
                                            
                                            # Only add if it's not empty and not just a number
                                            if main_effect and not main_effect.replace('.', '').replace('%', '').isdigit():
                                                effects_list.append(f"+{main_effect}")
                                                print(f"Added cleaned effect: '+{main_effect}'")
                                        
                                        print(f"Final effects list for {piece_name} level {level}: {effects_list}")
                                        processed_level['effects'] = effects_list
                                
                                processed_levels[level] = processed_level
                            
                            # Determine slot from piece name if slot is empty
                            slot = piece_data.get('slot', '')
                            if not slot:
                                if 'helm' in piece_name.lower() or 'hat' in piece_name.lower() or 'hood' in piece_name.lower():
                                    slot = 'Helm'
                                elif 'chest' in piece_name.lower() or 'breast' in piece_name.lower() or 'tunic' in piece_name.lower():
                                    slot = 'Chest'
                                elif 'pants' in piece_name.lower() or 'legs' in piece_name.lower():
                                    slot = 'Pants'
                            
                            # Add the processed piece to formatted_data
                            formatted_data['armor'][piece_name] = {
                                'type': 'armor',
                                'set': set_name,
                                'levels': processed_levels,
                                'slot': slot,
                                'min_level': piece_data.get('min_level'),
                                'max_level': piece_data.get('max_level')
                            }
                            
                            app.logger.debug(f"Added armor piece: {piece_name} with slot: {slot}")
        
        app.logger.info(f"Processed data summary:")
        app.logger.info(f"Weapons: {len(formatted_data['weapons'])} items")
        app.logger.info(f"Accessories: {len(formatted_data['accessories'])} items")
        app.logger.info(f"Armor: {len(formatted_data['armor'])} items")
        
        return jsonify(formatted_data)
        
    except Exception as e:
        app.logger.error(f"Error in get_all_stats: {str(e)}")
        app.logger.exception("Full traceback:")
        return jsonify({"error": str(e)}), 500

@app.route('/builds')
def builds_page():
    return render_template('builds.html', nav=set_nav_active('builds'))

@app.route('/compare')
def compare_builds():
    return render_template('compare.html', nav=set_nav_active('compare'))

@app.route('/guide')
def guide_page():
    return render_template('guide.html', nav=set_nav_active('guide'))

@app.route('/api/debug-stats')
def debug_stats():
    try:
        with open('scraped_json/core_keeper_weapons.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify({
            'raw_data': {
                'keys': list(data.keys()),
                'melee_count': len(data.get('melee', {})),
                'range_count': len(data.get('range', {})),
                'magic_count': len(data.get('magic', {})),
                'first_melee': next(iter(data.get('melee', {}).items()), None),
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)})

if not app.debug:
    file_handler = RotatingFileHandler('core_keeper.log', maxBytes=10240, backupCount=10)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('Core Keeper Calculator startup')

with app.app_context():
    db.create_all()

# Add this function to check for required files
def check_required_files():
    required_files = [
        'scraped_json/core_keeper_weapons.json',
        'scraped_json/core_keeper_accessories.json',
        'scraped_json/core_keeper_armor.json'
    ]
    
    missing_files = []
    for file_path in required_files:
        if not os.path.exists(file_path):
            missing_files.append(file_path)
    
    if missing_files:
        app.logger.error(f"Missing required files: {', '.join(missing_files)}")
        raise FileNotFoundError(f"Missing required files: {', '.join(missing_files)}")

# Add this before app.run()
if __name__ == '__main__':
    check_required_files()
    app.run(debug=True)
