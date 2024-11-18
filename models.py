from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from dataclasses import dataclass
from typing import Optional

db = SQLAlchemy()

class Weapon(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    stats = db.Column(db.JSON)

class WeaponStats(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    weapon_id = db.Column(db.Integer, db.ForeignKey('weapon.id'), nullable=False)
    level = db.Column(db.Integer, nullable=False)
    damage_low = db.Column(db.Float)
    damage_high = db.Column(db.Float)
    attack_speed = db.Column(db.Float)
    crit_chance = db.Column(db.Float)
    durability = db.Column(db.Float)
    mana_cost = db.Column(db.Float)
    effects = db.Column(db.String(500))

class Build(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Build components
    weapon_name = db.Column(db.String(100))
    armor_pieces = db.Column(db.JSON)  # Store as JSON array
    food_buffs = db.Column(db.JSON)    # Store as JSON array
    potion_buffs = db.Column(db.JSON)  # Store as JSON array
    skills = db.Column(db.JSON)        # Store as JSON array
    
    # Calculated stats
    total_dps = db.Column(db.Float)
    effective_damage = db.Column(db.Float)
    attack_speed = db.Column(db.Float)
    
    # Relationships
    weapon_stats_id = db.Column(db.Integer, db.ForeignKey('weapon_stats.id'))
    weapon_stats = db.relationship('WeaponStats', foreign_keys=[weapon_stats_id])
    weapon = db.relationship('Weapon', foreign_keys=[weapon_name])

@dataclass
class WeaponStatsData:
    damage_low: float
    damage_high: float
    attack_speed: float
    crit_chance: float
    level: int = 1

@dataclass
class WeaponData:
    name: str
    stats: WeaponStatsData
    description: Optional[str] = None