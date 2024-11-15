from flask import Flask, render_template, jsonify, request
from dataclasses import dataclass
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

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///core_keeper.db'
db.init_app(app)

class ItemType(Enum):
    WEAPON = "weapon"
    ARMOR = "armor"
    FOOD = "food"
    POTION = "potion"

@dataclass
class Item:
    name: str
    type: ItemType
    stats: Dict[str, float]
    description: str
    duration: Optional[int] = None  # Duration in seconds for food/potion buffs

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
        
        # Add weapon stats
        if self.weapon:
            for stat, value in self.weapon.stats.items():
                try:
                    # Convert value to float if it's a string
                    if isinstance(value, str):
                        value = float(value)
                    base_stats[stat] = base_stats.get(stat, 0.0) + value
                except (ValueError, TypeError) as e:
                    app.logger.error(f"Error converting stat {stat} with value {value}: {str(e)}")
                    continue

        # Add armor stats
        for armor in self.armor_pieces:
            for stat, value in armor.stats.items():
                try:
                    if isinstance(value, str):
                        value = float(value)
                    base_stats[stat] = base_stats.get(stat, 0.0) + value
                except (ValueError, TypeError) as e:
                    app.logger.error(f"Error converting armor stat {stat}: {str(e)}")
                    continue

        # Add food buffs
        for food in self.food_buffs:
            for stat, value in food.stats.items():
                try:
                    if isinstance(value, str):
                        value = float(value)
                    base_stats[stat] = base_stats.get(stat, 0.0) + value
                except (ValueError, TypeError) as e:
                    app.logger.error(f"Error converting food stat {stat}: {str(e)}")
                    continue

        # Add potion buffs
        for potion in self.potion_buffs:
            for stat, value in potion.stats.items():
                try:
                    if isinstance(value, str):
                        value = float(value)
                    base_stats[stat] = base_stats.get(stat, 0.0) + value
                except (ValueError, TypeError) as e:
                    app.logger.error(f"Error converting potion stat {stat}: {str(e)}")
                    continue

        # Apply skill modifiers
        for skill in self.skills:
            for stat, value in skill.stats.items():
                try:
                    if isinstance(value, str):
                        value = float(value)
                    if stat.endswith('_multiplier'):
                        base_stat = stat.replace('_multiplier', '')
                        base_stats[base_stat] = base_stats.get(base_stat, 0.0) * value
                    else:
                        base_stats[stat] = base_stats.get(stat, 0.0) + value
                except (ValueError, TypeError) as e:
                    app.logger.error(f"Error converting skill stat {stat}: {str(e)}")
                    continue

        # Calculate DPS using average damage
        avg_damage = (base_stats['damage_high'] + base_stats['damage_low']) / 2 if 'damage_high' in base_stats else base_stats['damage']
        base_damage = avg_damage * base_stats['damage_multiplier']
        crit_dps = base_damage * base_stats['crit_multiplier'] * base_stats['crit_chance']
        normal_dps = base_damage * (1 - base_stats['crit_chance'])
        total_dps = (crit_dps + normal_dps) * base_stats['attack_speed']

        return {
            'base_stats': base_stats,
            'total_dps': total_dps,
            'effective_damage_per_hit': base_damage,
            'attacks_per_second': base_stats['attack_speed']
        }

ITEMS_DB = []

def load_game_data():
    """
    Loads game data from local JSON file
    """
    try:
        with open('core_keeper_weapons.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            items = []
            
            # Process melee weapons
            for weapon_name, weapon_data in data.get('melee', {}).items():
                for level, level_data in weapon_data.get('levels', {}).items():
                    try:
                        # Parse damage range (format: "30-36")
                        damage_str = level_data.get('damage', '0-0')
                        damage_low, damage_high = map(float, damage_str.replace('\u2212', '-').split('-'))
                        
                        # Parse attack rate
                        attack_rate = float(level_data.get('attack rate', 1.0))
                        
                        # Parse effects for crit chance
                        effects = level_data.get('effects', '')
                        crit_chance = 0.05  # default
                        if effects:
                            crit_match = re.search(r'(\d+(?:\.\d+)?)% critical hit chance', effects)
                            if crit_match:
                                crit_chance = float(crit_match.group(1)) / 100

                        # Handle durability
                        durability = level_data.get('durability', 100)
                        if isinstance(durability, str) and durability.lower() == 'infinite':
                            durability = float('inf')
                        else:
                            try:
                                durability = float(durability)
                            except (ValueError, TypeError):
                                durability = 100.0
                        
                        item = {
                            'name': f"{weapon_name} (Level {level})",
                            'type': 'weapon',
                            'stats': {
                                'damage_low': damage_low,
                                'damage_high': damage_high,
                                'damage': (damage_low + damage_high) / 2,
                                'attack_speed': attack_rate,
                                'crit_chance': crit_chance,
                                'level': int(level),
                                'rarity': level_data.get('rarity', 'Common'),
                                'durability': durability
                            },
                            'description': level_data.get('tooltip', ''),
                            'effects': level_data.get('effects', '')
                        }
                        items.append(item)
                        app.logger.info(f"Added weapon: {item['name']}")
                    except Exception as e:
                        app.logger.error(f"Error processing level {level} for {weapon_name}: {str(e)}")

            # Process magic weapons
            for weapon_name, weapon_data in data.get('magic', {}).items():
                for level, level_data in weapon_data.get('levels', {}).items():
                    try:
                        damage_str = level_data.get('damage', '0-0')
                        damage_low, damage_high = map(float, damage_str.replace('\u2212', '-').split('-'))
                        
                        item = {
                            'name': f"{weapon_name} (Level {level})",
                            'type': 'weapon',
                            'stats': {
                                'damage_low': damage_low,
                                'damage_high': damage_high,
                                'damage': (damage_low + damage_high) / 2,
                                'attack_speed': float(level_data.get('attack rate', 1.0)),
                                'crit_chance': 0.05,
                                'level': int(level),
                                'rarity': level_data.get('rarity', 'Common'),
                                'durability': float(level_data.get('durability', 100)),
                                'mana_cost': float(level_data.get('mana', 0))
                            },
                            'description': level_data.get('tooltip', ''),
                            'effects': level_data.get('effects', '')
                        }
                        items.append(item)
                        app.logger.info(f"Added magic weapon: {item['name']}")
                    except Exception as e:
                        app.logger.error(f"Error processing level {level} for {weapon_name}: {str(e)}")
            
            app.logger.info(f"Loaded {len(items)} total items")
            return items
            
    except Exception as e:
        app.logger.error(f"Error loading core_keeper_weapons.json: {str(e)}")
        app.logger.exception(e)
        return []

# Add these constants
DATA_FILE = "game_data.json"
DATA_REFRESH_INTERVAL = timedelta(days=1)  # Update data daily

def initialize_data():
    global ITEMS_DB
    ITEMS_DB = []
    game_data = load_game_data()
    
    app.logger.info(f"Loaded game data with {len(game_data)} items")
    
    # Convert data to Item objects
    try:
        for item_data in game_data:
            try:
                # Ensure type is converted to ItemType enum
                item_type = item_data['type']
                if isinstance(item_type, str):
                    item_type = ItemType(item_type.lower())
                
                ITEMS_DB.append(Item(
                    name=item_data['name'],
                    type=item_type,
                    stats=item_data['stats'],
                    description=item_data.get('description', '')
                ))
                app.logger.info(f"Added item: {item_data['name']}")
            except Exception as e:
                app.logger.error(f"Error adding item {item_data}: {str(e)}")
    except Exception as e:
        app.logger.error(f"Error initializing data: {str(e)}")

    app.logger.info(f"Initialized {len(ITEMS_DB)} items")

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
        with open('core_keeper_weapons.json', 'r', encoding='utf-8') as f:
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
    if not ITEMS_DB:  # Initialize data if not already done
        initialize_data()
    data = request.get_json()
    
    # Create build from request data
    build = Build(
        name=data.get('name', 'Custom Build'),
        weapon=next((item for item in ITEMS_DB if item.name == data['weapon']), None),
        armor_pieces=[item for item in ITEMS_DB if item.name in data.get('armor', [])],
        food_buffs=[item for item in ITEMS_DB if item.name in data.get('food', [])],
        potion_buffs=[item for item in ITEMS_DB if item.name in data.get('potions', [])],
        skills=[skill for skill in SKILLS_DB if skill.name in data.get('skills', [])],
        description=data.get('description', '')
    )
    
    return jsonify(build.calculate_dps())

@app.route('/stats')
def stats_page():
    if not ITEMS_DB:
        initialize_data()
    return render_template('stats.html', nav=set_nav_active('stats'))

@app.route('/api/all-stats')
def get_all_stats():
    try:
        with open('core_keeper_weapons.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        formatted_data = {
            'weapons': {}
        }
        
        # Process each weapon type
        for weapon_type in ['melee', 'range', 'magic']:
            for weapon_name, weapon_data in data.get(weapon_type, {}).items():
                if weapon_data.get('levels'):
                    formatted_data['weapons'][weapon_name] = {
                        'type': weapon_type,
                        'levels': {
                            str(level): {
                                'damage': level_data.get('damage', '0-0'),
                                'attack_rate': float(level_data.get('attack rate', 1.0)),
                                'crit_chance': float(level_data.get('crit_chance', 0.05)),
                                'durability': level_data.get('durability', 100),
                                'rarity': level_data.get('rarity', 'Common'),
                                'effects': level_data.get('effects', ''),
                                'tooltip': level_data.get('tooltip', ''),
                                'mana': level_data.get('mana', None)
                            }
                            for level, level_data in weapon_data['levels'].items()
                        }
                    }
        
        app.logger.info(f"Processed {len(formatted_data['weapons'])} weapons")
        return jsonify(formatted_data)
        
    except Exception as e:
        app.logger.error(f"Error in get_all_stats: {str(e)}")
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
        with open('core_keeper_weapons.json', 'r', encoding='utf-8') as f:
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

if __name__ == '__main__':
    app.run(debug=True)
