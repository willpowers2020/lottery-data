#!/usr/bin/env python3
"""
Pick 4/5 Prediction Tool - OPTIMIZED VERSION
=============================================

This version supports THREE database backends:
  1. sqlite   - Local SQLite databases
  2. mongo    - Original MongoDB (lotterypost collection)  
  3. mongo_v2 - Optimized MongoDB (lottery_v2 collection)

Toggle via URL: ?db=sqlite, ?db=mongo, or ?db=mongo_v2

PERFORMANCE COMPARISON:
=======================
Original Schema:
  - numbers stored as JSON string: "[\"3\", \"1\", \"8\", \"0\"]"
  - Must parse JSON for every document
  - No pre-calculated normalized/pairs fields
  - Queries require full table scans for pattern matching

Optimized Schema:
  - numbers as native array: ["3", "1", "8", "0"]
  - Pre-calculated: normalized, digits_sum, pairs_2dp, triples_3dp
  - Compound indexes on common query patterns
  - 10-50x faster for prediction algorithms
"""

from flask import Flask, render_template, jsonify, request
import os
import json
from datetime import datetime, timedelta
from collections import Counter
from itertools import combinations as iter_combinations
from pathlib import Path
import sqlite3
import hashlib

app = Flask(__name__)

# CORS support — allows mld_platform.html to call the API from file:// or any origin
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
    response.headers.add('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
    return response

# =============================================================================
# QUERY BILLING & COST ESTIMATION
# =============================================================================

QUERY_COST_CONFIG = {
    'efficacy_report': {
        'base_cost': 0.00,
        'per_seed_cost': 0.001,
        'threshold_seeds': 50,
        'threshold_time_seconds': 15,
    },
    'consecutive_draws': {
        'base_cost': 0.00,
        'per_state_cost': 0.01,
        'per_day_cost': 0.001,
        'threshold_states': 3,
        'threshold_days': 7,
        'threshold_time_seconds': 15,
    },
}

# In-memory job store (replace with Redis/Celery in production)
_background_jobs = {}

def estimate_query_cost(query_type, params):
    """Estimate the cost and time for a query."""
    if query_type == 'efficacy_report':
        return _estimate_efficacy_cost(params)
    elif query_type == 'consecutive_draws':
        return _estimate_consecutive_cost(params)
    return {'is_heavy': False, 'estimated_cost': 0, 'estimated_time_seconds': 5}

def _estimate_efficacy_cost(params):
    config = QUERY_COST_CONFIG['efficacy_report']
    start = datetime.strptime(params.get('start_date', '2026-01-01'), '%Y-%m-%d')
    end = datetime.strptime(params.get('end_date', '2026-01-15'), '%Y-%m-%d')
    days = (end - start).days + 1
    estimated_seeds = days * 2
    
    game_type = params.get('game_type', 'pick4')
    pair_size = params.get('pair_size', 2)
    candidate_estimates = {
        'pick2': {1: 10},
        'pick3': {1: 220, 2: 55},
        'pick4': {1: 715, 2: 330, 3: 120},
        'pick5': {1: 2002, 2: 715, 3: 252, 4: 126},
    }
    estimated_candidates = candidate_estimates.get(game_type, {}).get(pair_size, 500)
    estimated_time = (estimated_seeds * estimated_candidates * 0.0001) + 2
    
    cost = 0
    if estimated_seeds > config['threshold_seeds']:
        cost = (estimated_seeds - config['threshold_seeds']) * config['per_seed_cost']
    
    is_heavy = estimated_time > config['threshold_time_seconds']
    
    return {
        'estimated_seeds': estimated_seeds,
        'estimated_candidates': estimated_candidates,
        'estimated_time_seconds': round(estimated_time, 1),
        'estimated_cost': round(cost, 4),
        'is_heavy': is_heavy,
        'is_chargeable': cost > 0,
        'warnings': [f"~{int(estimated_time)}s query time"] if is_heavy else [],
        'recommendation': 'background' if is_heavy else 'immediate'
    }

def _estimate_consecutive_cost(params):
    config = QUERY_COST_CONFIG['consecutive_draws']
    start = datetime.strptime(params.get('start_date', '2026-01-01'), '%Y-%m-%d')
    end = datetime.strptime(params.get('end_date', '2026-01-01'), '%Y-%m-%d')
    days = (end - start).days + 1
    states = params.get('states', ['All'])
    num_states = 10 if 'All' in states else len(states)
    
    estimated_time = (num_states * days * 0.5) + 2
    
    cost = 0
    if num_states > config['threshold_states']:
        cost += (num_states - config['threshold_states']) * config['per_state_cost']
    if days > config['threshold_days']:
        cost += (days - config['threshold_days']) * config['per_day_cost']
    
    is_heavy = estimated_time > config['threshold_time_seconds']
    
    return {
        'num_states': num_states,
        'num_days': days,
        'estimated_time_seconds': round(estimated_time, 1),
        'estimated_cost': round(cost, 4),
        'is_heavy': is_heavy,
        'is_chargeable': cost > 0,
        'warnings': [f"~{int(estimated_time)}s query time"] if is_heavy else [],
        'recommendation': 'background' if is_heavy else 'immediate'
    }

def create_background_job(job_type, params, user_email):
    """Create a background job for heavy queries."""
    job_id = hashlib.md5(f"{job_type}{json.dumps(params, sort_keys=True, default=str)}{datetime.now().isoformat()}".encode()).hexdigest()[:12]
    _background_jobs[job_id] = {
        'id': job_id,
        'type': job_type,
        'params': params,
        'user_email': user_email,
        'status': 'queued',
        'created_at': datetime.now().isoformat(),
        'completed_at': None,
        'result': None,
        'error': None
    }
    return job_id

def get_job_status(job_id):
    return _background_jobs.get(job_id)

# =============================================================================
# CONFIGURATION
# =============================================================================

DEFAULT_DB_MODE = os.environ.get('DB_MODE', 'mongo_v2')  # sqlite, mongo, mongo_v2

# SQLite paths
PICK4_DB_PATH = Path(os.environ.get('PICK4_DB_PATH', '/Users/british.williams/lottery_scraper/pick4/data/pick4_master.db'))
PICK5_DB_PATH = Path(os.environ.get('PICK5_DB_PATH', '/Users/british.williams/lottery_scraper/pick5/data/pick5_data.db'))

# MongoDB
MONGO_URL = os.environ.get('MONGO_URL', '')
MONGO_DB = 'lottery'
MONGO_COLLECTION_ORIGINAL = 'lotterypost'        # Original schema
MONGO_COLLECTION_OPTIMIZED = 'lottery_v2'  # New optimized schema

# Lazy-loaded connections
_mongo_client = None

def get_mongo_client():
    global _mongo_client
    if _mongo_client is None:
        from pymongo import MongoClient
        _mongo_client = MongoClient(MONGO_URL)
    return _mongo_client


# =============================================================================
# DATABASE MODE HELPERS
# =============================================================================

def get_db_mode():
    """Get current database mode from request param or default."""
    return request.args.get('db', DEFAULT_DB_MODE).lower()

def get_collection():
    """Get the appropriate database collection based on mode."""
    mode = get_db_mode()
    
    if mode == 'sqlite':
        return SQLiteAdapter(PICK4_DB_PATH, PICK5_DB_PATH)
    elif mode == 'mongo_v2':
        client = get_mongo_client()
        return MongoOptimizedAdapter(client[MONGO_DB][MONGO_COLLECTION_OPTIMIZED])
    else:  # mongo (original)
        client = get_mongo_client()
        return MongoOriginalAdapter(client[MONGO_DB][MONGO_COLLECTION_ORIGINAL])


# =============================================================================
# MONGO OPTIMIZED ADAPTER (NEW SCHEMA)
# =============================================================================

class MongoOptimizedAdapter:
    """
    Adapter for optimized MongoDB schema.
    Takes advantage of pre-calculated fields for faster queries.
    """
    
    def __init__(self, collection):
        self.collection = collection
    
    def distinct(self, field, query=None):
        """Get distinct values."""
        # Map field names
        field_map = {'state_name': 'state_name', 'game_name': 'game_name', 'country': 'country'}
        mongo_field = field_map.get(field, field)
        return self.collection.distinct(mongo_field, query or {})
    
    def find(self, query, projection=None):
        """Find documents - returns cursor-like object."""
        # Transform query for optimized schema
        mongo_query = self._transform_query(query)
        cursor = self.collection.find(mongo_query, projection)
        return MongoOptimizedCursor(cursor)
    
    def find_one(self, query, sort=None):
        """Find single document."""
        mongo_query = self._transform_query(query)
        if sort:
            return self.collection.find_one(mongo_query, sort=sort)
        return self.collection.find_one(mongo_query)
    
    def find_by_normalized(self, normalized, state=None, game_type=None):
        """
        FAST: Find all draws matching a normalized pattern.
        Uses indexed 'normalized' field.
        """
        query = {'normalized': normalized.replace('-', '')}
        if state:
            query['state'] = self._state_name_to_code(state)
        if game_type:
            query['game_type'] = game_type
        return list(self.collection.find(query).sort('date', 1))
    
    def find_by_pairs(self, pairs, state=None, game_type='pick4'):
        """
        FAST: Find draws containing specific 2DP pairs.
        Uses indexed 'pairs_2dp' field.
        """
        query = {'pairs_2dp': {'$in': pairs}, 'game_type': game_type}
        if state:
            query['state'] = self._state_name_to_code(state)
        return list(self.collection.find(query).sort('date', 1))
    
    def _transform_query(self, query):
        """Transform query for optimized schema."""
        mongo_query = {}
        
        for key, value in query.items():
            if key == 'state_name':
                # Can query by state_name (full name) or state (code)
                mongo_query['state_name'] = value
            elif key == 'game_name':
                if isinstance(value, dict) and '$in' in value:
                    # Convert game names to game codes
                    mongo_query['game_name'] = {'$in': value['$in']}
                else:
                    mongo_query['game_name'] = value
            elif key == 'date':
                mongo_query['date'] = value
            elif key == '$or':
                mongo_query['$or'] = value
            else:
                mongo_query[key] = value
        
        return mongo_query
    
    def _state_name_to_code(self, name):
        """Convert state name to code."""
        mapping = {
            'california': 'ca', 'florida': 'fl', 'texas': 'tx', 'new york': 'ny',
            'washington dc': 'dc', 'georgia': 'ga', 'ohio': 'oh', 'pennsylvania': 'pa',
            'illinois': 'il', 'michigan': 'mi', 'new jersey': 'nj', 'virginia': 'va',
            'maryland': 'md', 'north carolina': 'nc', 'south carolina': 'sc',
            'tennessee': 'tn', 'kentucky': 'ky', 'indiana': 'in', 'missouri': 'mo',
            'wisconsin': 'wi', 'arkansas': 'ar', 'louisiana': 'la', 'iowa': 'ia',
            'connecticut': 'ct', 'delaware': 'de', 'west virginia': 'wv', 'oregon': 'or',
            'new mexico': 'nm', 'massachusetts': 'ma'
        }
        return mapping.get(name.lower(), name.lower())


class MongoOptimizedCursor:
    """Cursor wrapper for optimized MongoDB results."""
    
    def __init__(self, cursor):
        self.cursor = cursor
    
    def sort(self, field, direction=1):
        if isinstance(field, list):
            self.cursor = self.cursor.sort(field)
        else:
            self.cursor = self.cursor.sort(field, direction)
        return self
    
    def limit(self, n):
        self.cursor = self.cursor.limit(n)
        return self
    
    def __iter__(self):
        for doc in self.cursor:
            # Transform to common format expected by app
            yield {
                'country': doc.get('country', 'United States'),
                'state_name': doc.get('state_name', ''),
                'game_name': doc.get('game_name', ''),
                'date': doc.get('date'),
                'numbers': doc.get('numbers', '[]') if isinstance(doc.get('numbers'), str) else json.dumps(doc.get('numbers', [])),  # Keep as JSON string for compatibility
                'tod': doc.get('tod', ''),
                # Extra optimized fields available
                '_normalized': doc.get('normalized'),
                '_pairs_2dp': doc.get('pairs_2dp'),
                '_digits_sum': doc.get('digits_sum')
            }


# =============================================================================
# MONGO ORIGINAL ADAPTER
# =============================================================================

class MongoOriginalAdapter:
    """Adapter for original MongoDB schema (lotterypost collection)."""
    
    def __init__(self, collection):
        self.collection = collection
    
    def distinct(self, field, query=None):
        return self.collection.distinct(field, query or {})
    
    def find(self, query, projection=None):
        cursor = self.collection.find(query, projection)
        return MongoCursor(cursor)
    
    def find_one(self, query, sort=None):
        if sort:
            return self.collection.find_one(query, sort=sort)
        return self.collection.find_one(query)
    
    def aggregate(self, pipeline, allowDiskUse=False):
        return self.collection.aggregate(pipeline, allowDiskUse=allowDiskUse)


class MongoCursor:
    """Simple cursor wrapper."""
    
    def __init__(self, cursor):
        self.cursor = cursor
    
    def sort(self, field, direction=1):
        if isinstance(field, list):
            self.cursor = self.cursor.sort(field)
        else:
            self.cursor = self.cursor.sort(field, direction)
        return self
    
    def limit(self, n):
        self.cursor = self.cursor.limit(n)
        return self
    
    def __iter__(self):
        return iter(self.cursor)


# =============================================================================
# SQLITE ADAPTER (unchanged from previous version)
# =============================================================================

class SQLiteAdapter:
    """Adapter for SQLite databases."""
    
    def __init__(self, pick4_path, pick5_path):
        self.pick4_path = Path(pick4_path)
        self.pick5_path = Path(pick5_path)
    
    def _get_conn(self, game_type='pick4'):
        if game_type in ['pick5', 'fantasy5', 'cash5']:
            if self.pick5_path.exists():
                return sqlite3.connect(self.pick5_path)
            return None
        else:
            if self.pick4_path.exists():
                return sqlite3.connect(self.pick4_path)
            return None
    
    def _state_code_to_name(self, code):
        mapping = {
            'al': 'Alabama', 'ak': 'Alaska', 'az': 'Arizona', 'ar': 'Arkansas',
            'ca': 'California', 'co': 'Colorado', 'ct': 'Connecticut', 'de': 'Delaware',
            'dc': 'Washington DC', 'fl': 'Florida', 'ga': 'Georgia', 'hi': 'Hawaii',
            'id': 'Idaho', 'il': 'Illinois', 'in': 'Indiana', 'ia': 'Iowa',
            'ks': 'Kansas', 'ky': 'Kentucky', 'la': 'Louisiana', 'me': 'Maine',
            'md': 'Maryland', 'ma': 'Massachusetts', 'mi': 'Michigan', 'mn': 'Minnesota',
            'ms': 'Mississippi', 'mo': 'Missouri', 'mt': 'Montana', 'ne': 'Nebraska',
            'nv': 'Nevada', 'nh': 'New Hampshire', 'nj': 'New Jersey', 'nm': 'New Mexico',
            'ny': 'New York', 'nc': 'North Carolina', 'nd': 'North Dakota', 'oh': 'Ohio',
            'ok': 'Oklahoma', 'or': 'Oregon', 'pa': 'Pennsylvania', 'ri': 'Rhode Island',
            'sc': 'South Carolina', 'sd': 'South Dakota', 'tn': 'Tennessee', 'tx': 'Texas',
            'ut': 'Utah', 'vt': 'Vermont', 'va': 'Virginia', 'wa': 'Washington',
            'wv': 'West Virginia', 'wi': 'Wisconsin', 'wy': 'Wyoming'
        }
        return mapping.get(code.lower(), code.upper())
    
    def _state_name_to_code(self, name):
        mapping = {
            'alabama': 'al', 'alaska': 'ak', 'arizona': 'az', 'arkansas': 'ar',
            'california': 'ca', 'colorado': 'co', 'connecticut': 'ct', 'delaware': 'de',
            'washington dc': 'dc', 'florida': 'fl', 'georgia': 'ga', 'hawaii': 'hi',
            'idaho': 'id', 'illinois': 'il', 'indiana': 'in', 'iowa': 'ia',
            'kansas': 'ks', 'kentucky': 'ky', 'louisiana': 'la', 'maine': 'me',
            'maryland': 'md', 'massachusetts': 'ma', 'michigan': 'mi', 'minnesota': 'mn',
            'mississippi': 'ms', 'missouri': 'mo', 'montana': 'mt', 'nebraska': 'ne',
            'nevada': 'nv', 'new hampshire': 'nh', 'new jersey': 'nj', 'new mexico': 'nm',
            'new york': 'ny', 'north carolina': 'nc', 'north dakota': 'nd', 'ohio': 'oh',
            'oklahoma': 'ok', 'oregon': 'or', 'pennsylvania': 'pa', 'rhode island': 'ri',
            'south carolina': 'sc', 'south dakota': 'sd', 'tennessee': 'tn', 'texas': 'tx',
            'utah': 'ut', 'vermont': 'vt', 'virginia': 'va', 'washington': 'wa',
            'west virginia': 'wv', 'wisconsin': 'wi', 'wyoming': 'wy'
        }
        return mapping.get(name.lower(), name.lower())
    
    def _get_tod_from_game(self, game_name):
        game_lower = game_name.lower()
        if any(x in game_lower for x in ['evening', 'night', 'eve', 'pm', '10pm', '7pm']):
            return 'Evening'
        if any(x in game_lower for x in ['midday', 'mid-day', 'day', '1pm', '4pm']):
            return 'Midday'
        if 'morning' in game_lower:
            return 'Morning'
        return ''
    
    def distinct(self, field, query=None):
        results = set()
        for game_type in ['pick4', 'pick5']:
            conn = self._get_conn(game_type)
            if not conn:
                continue
            cursor = conn.cursor()
            table = 'pick4_results' if game_type == 'pick4' else 'pick5_results'
            try:
                if field == 'country':
                    results.add('United States')
                elif field == 'state_name':
                    cursor.execute(f'SELECT DISTINCT state FROM {table}')
                    for row in cursor.fetchall():
                        results.add(self._state_code_to_name(row[0]))
                elif field == 'game_name':
                    if query and 'state_name' in query:
                        state_code = self._state_name_to_code(query['state_name'])
                        cursor.execute(f'SELECT DISTINCT game FROM {table} WHERE state = ?', (state_code,))
                    else:
                        cursor.execute(f'SELECT DISTINCT game FROM {table}')
                    for row in cursor.fetchall():
                        # Convert 'daily-4' to 'Daily 4'
                        display_name = row[0].replace('-', ' ').title()
                        results.add(display_name)
            except Exception as e:
                print(f"SQLite distinct error ({game_type}): {e}")
            conn.close()
        return list(results)
    
    def find(self, query, projection=None):
        results = []
        game_types_to_check = ['pick4', 'pick5']
        
        if query.get('game_name'):
            game_names = []
            if isinstance(query['game_name'], dict) and '$in' in query['game_name']:
                game_names = query['game_name']['$in']
            elif isinstance(query['game_name'], str):
                game_names = [query['game_name']]
            
            for gn in game_names:
                gn_lower = gn.lower()
                if any(x in gn_lower for x in ['pick 5', 'pick5', 'daily 5']):
                    game_types_to_check = ['pick5']
                    break
                elif any(x in gn_lower for x in ['pick 4', 'pick4', 'daily 4', 'daily-4', 'dc-4', 'dc 4']):
                    game_types_to_check = ['pick4']
                    break
        
        for game_type in game_types_to_check:
            conn = self._get_conn(game_type)
            if not conn:
                continue
            cursor = conn.cursor()
            table = 'pick4_results' if game_type == 'pick4' else 'pick5_results'
            
            # Pick4 schema: id, state, game, draw_date, draw_time, num1, num2, num3, num4, bonus, created_at
            # Pick5 schema: id, state, game, draw_date, numbers, fireball, jackpot, created_at
            if game_type == 'pick4':
                sql = f'SELECT state, game, draw_date, draw_time, num1, num2, num3, num4 FROM {table} WHERE 1=1'
            else:
                sql = f'SELECT state, game, draw_date, numbers FROM {table} WHERE 1=1'
            params = []
            
            if 'state_name' in query:
                state_code = self._state_name_to_code(query['state_name'])
                sql += ' AND state = ?'
                params.append(state_code)
            
            if 'game_name' in query:
                if isinstance(query['game_name'], dict) and '$in' in query['game_name']:
                    game_codes = [self._normalize_game_name_to_db(gn) for gn in query['game_name']['$in']]
                    placeholders = ','.join(['?' for _ in game_codes])
                    sql += f' AND game IN ({placeholders})'
                    params.extend(game_codes)
                elif isinstance(query['game_name'], str):
                    sql += ' AND game = ?'
                    params.append(self._normalize_game_name_to_db(query['game_name']))
            
            if 'date' in query:
                if '$gte' in query['date']:
                    sql += ' AND draw_date >= ?'
                    d = query['date']['$gte']
                    params.append(d.strftime('%Y-%m-%d') if hasattr(d, 'strftime') else d)
                if '$lt' in query['date']:
                    sql += ' AND draw_date < ?'
                    d = query['date']['$lt']
                    params.append(d.strftime('%Y-%m-%d') if hasattr(d, 'strftime') else d)
            
            sql += ' ORDER BY draw_date ASC'
            
            try:
                cursor.execute(sql, params)
                for row in cursor.fetchall():
                    if game_type == 'pick4':
                        state_code, game, draw_date, draw_time, n1, n2, n3, n4 = row
                        nums = [str(n1), str(n2), str(n3), str(n4)]
                        tod = self._parse_draw_time(draw_time, game)
                    else:
                        state_code, game, draw_date, numbers_str = row
                        # Parse numbers - could be "1-2-3-4-5" or "12345" or similar
                        nums = self._parse_pick5_numbers(numbers_str)
                        tod = self._get_tod_from_game(game)
                    
                    if not nums or not all(n.isdigit() for n in nums):
                        continue
                    
                    results.append({
                        'country': 'United States',
                        'state_name': self._state_code_to_name(state_code),
                        'game_name': game.replace('-', ' ').title(),
                        'date': datetime.strptime(draw_date, '%Y-%m-%d'),
                        'numbers': json.dumps(nums),
                        'tod': tod
                    })
            except Exception as e:
                print(f"SQLite find error ({game_type}): {e}")
                import traceback
                traceback.print_exc()
            conn.close()
        
        return SQLiteCursor(results)
    
    def _normalize_game_name_to_db(self, name):
        """Convert display name to database format: 'Daily 4' -> 'daily-4'"""
        return name.lower().replace(' ', '-')
    
    def _parse_draw_time(self, draw_time, game_name):
        """Parse draw_time field or infer from game name."""
        if draw_time:
            dt_lower = str(draw_time).lower()
            if any(x in dt_lower for x in ['evening', 'night', 'pm', 'eve']):
                return 'Evening'
            if any(x in dt_lower for x in ['midday', 'mid', 'day', 'am']):
                return 'Midday'
            if 'morning' in dt_lower:
                return 'Morning'
        return self._get_tod_from_game(game_name)
    
    def _parse_pick5_numbers(self, numbers_str):
        """Parse Pick 5 numbers from various formats."""
        if not numbers_str:
            return []
        s = str(numbers_str).strip()
        # Try hyphen-separated: "1-2-3-4-5"
        if '-' in s:
            parts = s.split('-')
            if len(parts) == 5:
                return [p.strip() for p in parts]
        # Try space-separated: "1 2 3 4 5"
        if ' ' in s:
            parts = s.split()
            if len(parts) == 5:
                return parts
        # Try comma-separated: "1,2,3,4,5"
        if ',' in s:
            parts = s.split(',')
            if len(parts) == 5:
                return [p.strip() for p in parts]
        # Try plain digits: "12345"
        if s.isdigit() and len(s) == 5:
            return list(s)
        return []
    
    def find_one(self, query, sort=None):
        results = list(self.find(query))
        if sort:
            field, direction = sort[0] if isinstance(sort, list) else sort
            results.sort(key=lambda x: x.get(field, ''), reverse=(direction == -1))
        return results[0] if results else None


class SQLiteCursor:
    def __init__(self, results):
        self.results = results
        self._sort_field = None
        self._sort_dir = 1
        self._limit_val = None
    
    def sort(self, field, direction=1):
        if isinstance(field, str):
            self._sort_field = field
            self._sort_dir = direction
        elif isinstance(field, list):
            self._sort_field = field[0][0]
            self._sort_dir = field[0][1]
        return self
    
    def limit(self, n):
        self._limit_val = n
        return self
    
    def __iter__(self):
        results = self.results
        if self._sort_field:
            results = sorted(results, key=lambda x: x.get(self._sort_field, ''), 
                           reverse=(self._sort_dir == -1))
        if self._limit_val:
            results = results[:self._limit_val]
        return iter(results)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def parse_numbers(numbers_str):
    try:
        nums = json.loads(numbers_str)
        return [str(n) for n in nums]
    except:
        return []

def get_sorted_value(nums):
    if not nums:
        return ''
    try:
        return '-'.join(sorted(nums, key=lambda x: int(x)))
    except:
        return '-'.join(sorted(nums))

def get_2dp_pairs_pred(number):
    digits = list(str(number).replace('-', ''))
    pairs = []
    for combo in iter_combinations(digits, 2):
        pair = ''.join(sorted(combo, key=lambda x: int(x)))
        if pair not in pairs:
            pairs.append(pair)
    return sorted(pairs)

def generate_2dp_ap_candidates(pairs, num_digits=4):
    seen_normalized = set()
    candidates = []
    max_num = 10 ** num_digits
    for num in range(max_num):
        num_str = str(num).zfill(num_digits)
        norm = get_sorted_value(list(num_str))
        if norm in seen_normalized:
            continue
        digits_in_num = set(num_str)
        for pair in pairs:
            d1, d2 = pair[0], pair[1]
            if d1 in digits_in_num and d2 in digits_in_num:
                seen_normalized.add(norm)
                candidates.append(num_str)
                break
    return sorted(candidates)

def get_3dp_pairs_pred(number):
    digits = list(str(number).replace('-', ''))
    pairs = []
    for combo in iter_combinations(digits, 3):
        pair = ''.join(sorted(combo, key=lambda x: int(x)))
        if pair not in pairs:
            pairs.append(pair)
    return sorted(pairs)

def generate_3dp_ap_candidates(pairs, num_digits=5):
    seen_normalized = set()
    candidates = []
    max_num = 10 ** num_digits
    for num in range(max_num):
        num_str = str(num).zfill(num_digits)
        norm = get_sorted_value(list(num_str))
        if norm in seen_normalized:
            continue
        digits_in_num = list(num_str)
        for pair in pairs:
            d1, d2, d3 = pair[0], pair[1], pair[2]
            temp_digits = digits_in_num.copy()
            found = True
            for d in [d1, d2, d3]:
                if d in temp_digits:
                    temp_digits.remove(d)
                else:
                    found = False
                    break
            if found:
                seen_normalized.add(norm)
                candidates.append(num_str)
                break
    return sorted(candidates)


# =============================================================================
# UNIFIED DP FUNCTIONS (Supports any pair size: 1DP, 2DP, 3DP, 4DP)
# =============================================================================

def get_dp_pairs(number, pair_size):
    """
    Extract all unique digit pairs of given size from a number.
    
    Args:
        number: String or list of digits (e.g., "1234" or ["1","2","3","4"])
        pair_size: Size of pairs to extract (1, 2, 3, or 4)
    
    Returns:
        List of sorted digit pairs as strings
    """
    if isinstance(number, (list, tuple)):
        digits = [str(d) for d in number]
    else:
        digits = list(str(number).replace('-', '').replace(' ', ''))
    
    pairs = []
    for combo in iter_combinations(digits, pair_size):
        # Sort digits within pair for normalization
        pair = ''.join(sorted(combo, key=lambda x: int(x)))
        if pair not in pairs:
            pairs.append(pair)
    
    return sorted(pairs)


def number_contains_pair(number_digits, pair):
    """
    Check if a number contains all digits of a pair (with multiplicity).
    """
    temp_digits = list(number_digits)
    for d in pair:
        if d in temp_digits:
            temp_digits.remove(d)
        else:
            return False
    return True


def generate_dp_candidates(pairs, num_digits):
    """
    Generate all possible numbers that contain at least one of the given pairs.
    Works for any pair size (1DP, 2DP, 3DP, 4DP).
    
    Args:
        pairs: List of digit pairs to match
        num_digits: Number of digits in target numbers (3, 4, or 5)
    
    Returns:
        List of candidate numbers (normalized, no duplicates)
    """
    if not pairs:
        return []
    
    seen_normalized = set()
    candidates = []
    max_num = 10 ** num_digits
    
    for num in range(max_num):
        num_str = str(num).zfill(num_digits)
        norm = get_sorted_value(list(num_str))
        
        if norm in seen_normalized:
            continue
        
        digits_list = list(num_str)
        
        for pair in pairs:
            if number_contains_pair(digits_list, pair):
                seen_normalized.add(norm)
                candidates.append(num_str)
                break
    
    return sorted(candidates)

def get_games_for_prediction(state, game_type):
    collection = get_collection()
    all_games = collection.distinct('game_name', {'state_name': state})
    patterns = {
        # Pick 2 games
        'pick2': ['pick 2', 'pick2', 'pick-2', 'daily 2', 'daily2', 'play 2', 'play2', 'dc 2', 'dc2', 'cash 2', 'cash2'],
        # Pick 3 games
        'daily3': ['daily 3', 'daily3', 'daily-3', 'pick 3', 'pick3', 'pick-3', 'dc-3', 'dc 3', 'dc3', 'cash 3', 'cash-3', 'cash3', 'play 3', 'play-3', 'play3'],
        'pick3': ['pick 3', 'pick3', 'pick-3', 'daily 3', 'daily3', 'daily-3', 'dc-3', 'dc 3', 'dc3', 'cash 3', 'cash-3', 'cash3', 'play 3', 'play-3', 'play3'],
        # Pick 4 games
        'daily4': ['daily 4', 'daily4', 'daily-4', 'pick 4', 'pick4', 'pick-4', 'dc-4', 'dc 4', 'dc4', 'cash 4', 'cash-4', 'cash4', 'win 4', 'win-4', 'win4', 'play 4', 'play-4', 'play4'],
        'pick4': ['pick 4', 'pick4', 'pick-4', 'daily 4', 'daily4', 'daily-4', 'dc-4', 'dc 4', 'dc4', 'cash 4', 'cash-4', 'cash4', 'win 4', 'win-4', 'win4', 'play 4', 'play-4', 'play4'],
        # Pick 5 games
        'pick5': [
            # Pennsylvania - use specific TOD variants
            'pick 5 day', 'pick 5 evening', 'pick 5 midday',
            # Delaware - use specific TOD variants only
            'play 5 day', 'play 5 night',
            # Washington DC
            'dc 5 evening', 'dc 5 midday',
            # Georgia
            'georgia five evening', 'georgia five midday',
            # Generic fallbacks (only if no TOD variants exist)
            'pick 5', 'pick5',
            'daily 5', 'daily5',
            'cash 5', 'cash5',
            'dc 5', 'dc5',
            'play 5', 'play5',
            'georgia five', 'georgia 5',
        ],
        'fantasy5': ['fantasy 5', 'fantasy5', 'fantasy-5'],
    }
    pats = patterns.get(game_type.lower(), [game_type.lower()])
    matched = [g for g in all_games if any(p in g.lower() for p in pats)]
    
    # Remove parent games if child TOD variants exist (e.g., remove "Play 5" if "Play 5 Day" exists)
    filtered = []
    for game in matched:
        game_lower = game.lower()
        # Check if this is a parent game (no day/night/midday/evening suffix)
        is_parent = not any(tod in game_lower for tod in ['day', 'night', 'midday', 'evening'])
        if is_parent:
            # Check if any child variant exists
            has_child = any(
                g.lower().startswith(game_lower) and g.lower() != game_lower 
                for g in matched
            )
            if has_child:
                continue  # Skip parent, use children instead
        filtered.append(game)
    
    return filtered if filtered else matched


# =============================================================================
# ROUTES
# =============================================================================

@app.route('/')
def index():
    """Main dashboard page."""
    return render_template('dashboard.html')


@app.route('/legacy')
def legacy_index():
    """Legacy index page."""
    return render_template('index.html')


# =============================================================================
# UNIFIED NAVIGATION ROUTES
# =============================================================================

@app.route('/predictions')
def predictions_page():
    """Live predictions page."""
    return render_template('rbtl_predictions.html')


@app.route('/platform')
def platform_page():
    """New MLD platform UI — predictions + backtest."""
    return render_template('mld_platform.html')


@app.route('/backtest')
def backtest_page():
    """Backtest/proof page."""
    return render_template('rbtl_backtest.html')


@app.route('/analysis/rbtl')
def analysis_rbtl_page():
    """RBTL deep analysis page."""
    return render_template('rbtl_algorithm.html')


@app.route('/analysis/efficacy')
def analysis_efficacy_page():
    """DP Efficacy reports page."""
    return render_template('efficacy_reports.html')


@app.route('/analysis/consecutive')
def analysis_consecutive_page():
    """Consecutive draws analysis page."""
    return render_template('consecutive_draws.html')


@app.route('/analysis/patterns')
def analysis_patterns_page():
    """Game patterns page."""
    return render_template('game_patterns.html')



@app.route("/nexus")
def nexus_page():
    """Pick 5 Nexus Predictor."""
    return render_template("nexus_predictor.html")
@app.route('/settings')
def settings_page():
    """Settings page."""
    return render_template('settings.html')

@app.route('/api/db-status')
def db_status():
    """Check database status."""
    mode = get_db_mode()
    status = {
        'mode': mode,
        'available_modes': ['sqlite', 'mongo', 'mongo_v2'],
        'toggle_hint': '?db=sqlite, ?db=mongo, or ?db=mongo_v2'
    }
    
    if mode == 'sqlite':
        status['pick4_path'] = str(PICK4_DB_PATH)
        status['pick5_path'] = str(PICK5_DB_PATH)
        status['pick4_exists'] = PICK4_DB_PATH.exists()
        status['pick5_exists'] = PICK5_DB_PATH.exists()
        
        for db_name, db_path, table in [('pick4', PICK4_DB_PATH, 'pick4_results'), ('pick5', PICK5_DB_PATH, 'pick5_results')]:
            if db_path.exists():
                try:
                    conn = sqlite3.connect(db_path)
                    cursor = conn.cursor()
                    cursor.execute(f'SELECT COUNT(*) FROM {table}')
                    status[f'{db_name}_records'] = cursor.fetchone()[0]
                    cursor.execute(f'SELECT MIN(draw_date), MAX(draw_date) FROM {table}')
                    row = cursor.fetchone()
                    status[f'{db_name}_date_range'] = f"{row[0]} to {row[1]}"
                    conn.close()
                except Exception as e:
                    status[f'{db_name}_error'] = str(e)
    
    elif mode in ['mongo', 'mongo_v2']:
        collection_name = MONGO_COLLECTION_OPTIMIZED if mode == 'mongo_v2' else MONGO_COLLECTION_ORIGINAL
        status['collection'] = collection_name
        status['schema'] = 'optimized' if mode == 'mongo_v2' else 'original'
        
        try:
            client = get_mongo_client()
            coll = client[MONGO_DB][collection_name]
            status['records'] = coll.count_documents({})
            status['states'] = len(coll.distinct('state_name' if mode == 'mongo' else 'state'))
            
            # Get date range
            pipeline = [{'$group': {'_id': None, 'min': {'$min': '$date'}, 'max': {'$max': '$date'}}}]
            result = list(coll.aggregate(pipeline))
            if result:
                status['date_range'] = f"{result[0]['min'].strftime('%Y-%m-%d')} to {result[0]['max'].strftime('%Y-%m-%d')}"
        except Exception as e:
            status['error'] = str(e)
    
    return jsonify(status)


# =============================================================================
# QUERY TOOL ENDPOINTS (for index.html)
# =============================================================================

@app.route('/api/countries')
def get_countries():
    """Get list of countries."""
    collection = get_collection()
    countries = collection.distinct('country')
    countries = sorted([c for c in countries if c])
    return jsonify([{'id': c, 'name': c} for c in countries])

@app.route('/api/states/<country>')
def get_states(country):
    """Get states for a country."""
    collection = get_collection()
    if country == 'all':
        states = collection.distinct('state_name')
    else:
        states = collection.distinct('state_name', {'country': country})
    states = sorted([s for s in states if s])
    return jsonify([{'id': s, 'name': s} for s in states])

@app.route('/api/games/<state>')
def get_games(state):
    """Get games for a state."""
    collection = get_collection()
    games = collection.distinct('game_name', {'state_name': state})
    games = sorted([g for g in games if g])
    return jsonify([{'id': g, 'name': g} for g in games])

@app.route('/api/lookup', methods=['POST'])
def lookup_number():
    """Look up a number in the database."""
    collection = get_collection()
    data = request.json
    
    number = data.get('number', '').replace('-', '').replace(' ', '')
    state = data.get('state', '')
    game = data.get('game', '')
    
    if not number:
        return jsonify({'error': 'Number is required'}), 400
    
    # Build query
    query = {}
    if state:
        query['state_name'] = state
    if game:
        query['game_name'] = game
    
    # Get all matching draws
    draws = list(collection.find(query))
    
    # Filter by number (check if normalized matches)
    num_digits = len(number)
    search_normalized = get_sorted_value(list(number))
    
    results = []
    for d in draws:
        nums = parse_numbers(d.get('numbers', '[]'))
        if len(nums) != num_digits:
            continue
        draw_normalized = get_sorted_value(nums)
        if draw_normalized == search_normalized:
            results.append({
                'date': d['date'].strftime('%Y-%m-%d'),
                'state': d.get('state_name', ''),
                'game': d.get('game_name', ''),
                'value': '-'.join(nums),
                'normalized': draw_normalized,
                'tod': d.get('tod', '')
            })
    
    # Sort by date descending
    results.sort(key=lambda x: x['date'], reverse=True)
    
    return jsonify({
        'search_number': number,
        'search_normalized': search_normalized,
        'total_hits': len(results),
        'results': results[:100],  # Limit to 100 results
        'db_mode': get_db_mode()
    })


@app.route('/api/prediction/states')
def get_prediction_states():
    collection = get_collection()
    states = collection.distinct('state_name')
    return jsonify(sorted([s for s in states if s]))

@app.route('/api/prediction/games/<state>')
def get_prediction_games(state):
    collection = get_collection()
    games = collection.distinct('game_name', {'state_name': state})
    game_types = set()
    for g in games:
        gl = g.lower()
        if any(x in gl for x in ['daily 3', 'daily3', 'pick 3', 'pick3', 'dc-3', 'dc 3']): 
            game_types.add('daily3')
        if any(x in gl for x in ['daily 4', 'daily4', 'pick 4', 'pick4', 'dc-4', 'dc 4', 'cash 4', 'win 4']): 
            game_types.add('daily4')
        if any(x in gl for x in ['pick 5', 'pick5', 'daily 5']): 
            game_types.add('pick5')
        if any(x in gl for x in ['fantasy 5', 'fantasy5', 'cash 5', 'cash5']): 
            game_types.add('fantasy5')
    type_labels = {
        'daily3': 'Daily 3 / Pick 3', 
        'daily4': 'Daily 4 / Pick 4', 
        'pick5': 'Pick 5 / Daily 5', 
        'fantasy5': 'Fantasy 5 / Cash 5'
    }
    return jsonify([{'id': t, 'name': type_labels.get(t, t)} for t in sorted(game_types)])

@app.route('/api/prediction/latest/<state>/<game_type>')
def get_latest_draw(state, game_type):
    collection = get_collection()
    games = get_games_for_prediction(state, game_type)
    if not games:
        return jsonify({'error': 'No games found', 'db_mode': get_db_mode()}), 404
    
    query = {'state_name': state, 'game_name': {'$in': games}}
    latest = collection.find_one(query, sort=[('date', -1)])
    
    if latest:
        nums = parse_numbers(latest.get('numbers', '[]'))
        return jsonify({
            'date': latest['date'].strftime('%Y-%m-%d'),
            'value': '-'.join(nums),
            'normalized': get_sorted_value(nums),
            'game': latest['game_name'],
            'tod': latest.get('tod', ''),
            'db_mode': get_db_mode()
        })
    return jsonify({'error': 'No draws found', 'db_mode': get_db_mode()}), 404


@app.route('/api/prediction/draw-by-date/<state>/<game_type>/<draw_date>')
def get_draw_by_date(state, game_type, draw_date):
    """Get draw for a specific date."""
    collection = get_collection()
    games = get_games_for_prediction(state, game_type)
    if not games:
        return jsonify({'error': 'No games found', 'db_mode': get_db_mode()}), 404
    
    try:
        date_obj = datetime.strptime(draw_date, '%Y-%m-%d')
    except:
        return jsonify({'error': 'Invalid date format'}), 400
    
    # Query for draws on this specific date
    query = {
        'state_name': state,
        'game_name': {'$in': games},
        'date': {'$gte': date_obj, '$lt': date_obj + timedelta(days=1)}
    }
    
    # Check for TOD filter
    tod = request.args.get('tod', '')
    
    # Find all draws for this date
    draws = list(collection.find(query))
    
    if not draws:
        return jsonify({'error': f'No draw found for {draw_date}', 'db_mode': get_db_mode()}), 404
    
    # Filter by TOD if specified
    if tod:
        filtered = [d for d in draws if d.get('tod', '').lower() == tod.lower()]
        if filtered:
            draws = filtered
    
    # Return the first matching draw (or most recent if multiple)
    draw = draws[0]
    nums = parse_numbers(draw.get('numbers', '[]'))
    
    return jsonify({
        'date': draw['date'].strftime('%Y-%m-%d'),
        'value': '-'.join(nums),
        'normalized': get_sorted_value(nums),
        'game': draw['game_name'],
        'tod': draw.get('tod', ''),
        'db_mode': get_db_mode()
    })


@app.route('/api/prediction/2dp-ap', methods=['POST'])
def predict_2dp_ap():
    """2DP-AP Prediction for Pick 4."""
    collection = get_collection()
    data = request.json
    seed_number = data.get('seed_number', data.get('seed', '')).replace('"', '').replace('[', '').replace(']', '').replace('-', '').replace(' ', '')
    seed_date_str = data.get('seed_date')
    state = data.get('state', 'California')
    game_type = data.get('game_type', 'daily4')
    days_threshold = int(data.get('days_threshold', 30))
    
    if not seed_number or not seed_date_str:
        return jsonify({'error': 'seed_number and seed_date required'}), 400
    
    num_digits = len(seed_number)
    seed_date = datetime.strptime(seed_date_str, '%Y-%m-%d')
    normalized_seed = get_sorted_value(list(seed_number))
    
    pairs_2dp = get_2dp_pairs_pred(normalized_seed.replace('-', ''))
    candidates = generate_2dp_ap_candidates(pairs_2dp, num_digits)
    
    games = get_games_for_prediction(state, game_type)
    if not games:
        return jsonify({'error': f'No {game_type} games found for {state}', 'db_mode': get_db_mode()}), 404
    
    query = {'state_name': state, 'game_name': {'$in': games}}
    all_draws = list(collection.find(query).sort('date', 1))
    
    seed_hits = []
    all_draws_lookup = {}
    
    for d in all_draws:
        nums = parse_numbers(d.get('numbers', '[]'))
        if len(nums) == num_digits:
            norm = get_sorted_value(nums)
            norm_key = norm.replace('-', '')
            if norm_key not in all_draws_lookup:
                all_draws_lookup[norm_key] = []
            all_draws_lookup[norm_key].append({
                'date': d['date'], 
                'value': '-'.join(nums), 
                'tod': d.get('tod', '')
            })
            
            if norm.replace('-', '') == normalized_seed.replace('-', ''):
                seed_hits.append({
                    'date': d['date'], 
                    'value': '-'.join(nums), 
                    'tod': d.get('tod', ''), 
                    'date_diff': (seed_date - d['date']).days
                })
    
    qualified = {}
    qualified_before = {}
    
    for cand in candidates:
        cand_norm = get_sorted_value(list(cand))
        cand_hits = all_draws_lookup.get(cand_norm.replace('-', ''), [])
        
        qualifying_after = []
        qualifying_before = []
        
        for sh in seed_hits:
            for ch in cand_hits:
                days_diff = (ch['date'] - sh['date']).days
                if 0 < days_diff <= days_threshold:
                    qualifying_after.append({
                        'seed_date': sh['date'].strftime('%Y-%m-%d'),
                        'hit_date': ch['date'].strftime('%Y-%m-%d'),
                        'value': ch['value'],
                        'days_after': days_diff
                    })
                if -days_threshold <= days_diff < 0:
                    qualifying_before.append({
                        'seed_date': sh['date'].strftime('%Y-%m-%d'),
                        'hit_date': ch['date'].strftime('%Y-%m-%d'),
                        'value': ch['value'],
                        'days_before': abs(days_diff)
                    })
        
        if qualifying_after:
            qualified[cand] = {'normalized': cand_norm, 'hit_count': len(qualifying_after), 'hits': qualifying_after[:10]}
        if qualifying_before:
            qualified_before[cand] = {'normalized': cand_norm, 'hit_count': len(qualifying_before), 'hits': qualifying_before[:10]}
    
    sorted_qual = sorted(qualified.items(), key=lambda x: x[1]['hit_count'], reverse=True)
    sorted_qual_before = sorted(qualified_before.items(), key=lambda x: x[1]['hit_count'], reverse=True)
    common_numbers = set(qualified.keys()).intersection(set(qualified_before.keys()))
    
    return jsonify({
        'algorithm': '2DP-AP',
        'db_mode': get_db_mode(),
        'seed_number': seed_number,
        'seed_date': seed_date_str,
        'normalized_seed': normalized_seed,
        'state': state,
        'game_type': game_type,
        'days_threshold': days_threshold,
        'pairs_2dp': pairs_2dp,
        'total_2dp_candidates': len(candidates),
        'seed_historical_hits': len(seed_hits),
        'seed_history': [{'date': h['date'].strftime('%Y-%m-%d'), 'value': h['value'], 'date_diff': h['date_diff']} for h in seed_hits],
        'qualified_count': len(qualified),
        'predictions': [{'number': num, **info} for num, info in sorted_qual],
        'all_numbers': sorted([num for num, _ in sorted_qual]),
        'qualified_before_count': len(qualified_before),
        'predictions_before': [{'number': num, **info} for num, info in sorted_qual_before],
        'all_numbers_before': sorted([num for num, _ in sorted_qual_before]),
        'common_count': len(common_numbers),
        'common_numbers': sorted(list(common_numbers))
    })

@app.route('/api/prediction/3dp-ap', methods=['POST'])
def predict_3dp_ap():
    """3DP-AP Prediction for Pick 5."""
    collection = get_collection()
    data = request.json
    seed_number = data.get('seed_number', data.get('seed', '')).replace('"', '').replace('[', '').replace(']', '').replace('-', '').replace(' ', '')
    seed_date_str = data.get('seed_date')
    state = data.get('state', 'California')
    days_threshold = int(data.get('days_threshold', 30))
    
    if not seed_number or not seed_date_str:
        return jsonify({'error': 'seed_number and seed_date required'}), 400
    
    if len(seed_number) != 5:
        return jsonify({'error': 'Seed number must be 5 digits for Pick 5'}), 400
    
    seed_date = datetime.strptime(seed_date_str, '%Y-%m-%d')
    normalized_seed = get_sorted_value(list(seed_number))
    
    pairs_3dp = get_3dp_pairs_pred(normalized_seed.replace('-', ''))
    candidates = generate_3dp_ap_candidates(pairs_3dp, 5)
    
    games = get_games_for_prediction(state, 'pick5')
    if not games:
        return jsonify({'error': f'No Pick 5 games found for {state}', 'db_mode': get_db_mode()}), 404
    
    query = {'state_name': state, 'game_name': {'$in': games}}
    all_draws = list(collection.find(query).sort('date', 1))
    
    seed_hits = []
    all_draws_lookup = {}
    
    for d in all_draws:
        nums = parse_numbers(d.get('numbers', '[]'))
        if len(nums) == 5:
            norm = get_sorted_value(nums)
            norm_key = norm.replace('-', '')
            if norm_key not in all_draws_lookup:
                all_draws_lookup[norm_key] = []
            all_draws_lookup[norm_key].append({
                'date': d['date'],
                'value': '-'.join(nums),
                'tod': d.get('tod', '')
            })
            
            if norm.replace('-', '') == normalized_seed.replace('-', ''):
                seed_hits.append({
                    'date': d['date'],
                    'value': '-'.join(nums),
                    'tod': d.get('tod', ''),
                    'date_diff': (seed_date - d['date']).days
                })
    
    qualified = {}
    qualified_before = {}
    
    for cand in candidates:
        cand_norm = get_sorted_value(list(cand))
        cand_hits = all_draws_lookup.get(cand_norm.replace('-', ''), [])
        
        qualifying_after = []
        qualifying_before = []
        
        for sh in seed_hits:
            for ch in cand_hits:
                days_diff = (ch['date'] - sh['date']).days
                if 0 < days_diff <= days_threshold:
                    qualifying_after.append({
                        'seed_date': sh['date'].strftime('%Y-%m-%d'),
                        'hit_date': ch['date'].strftime('%Y-%m-%d'),
                        'value': ch['value'],
                        'days_after': days_diff
                    })
                elif -days_threshold <= days_diff < 0:
                    qualifying_before.append({
                        'seed_date': sh['date'].strftime('%Y-%m-%d'),
                        'hit_date': ch['date'].strftime('%Y-%m-%d'),
                        'value': ch['value'],
                        'days_before': abs(days_diff)
                    })
        
        if qualifying_after:
            qualified[cand] = {'normalized': cand_norm, 'hit_count': len(qualifying_after), 'hits': qualifying_after[:10]}
        if qualifying_before:
            qualified_before[cand] = {'normalized': cand_norm, 'hit_count': len(qualifying_before), 'hits': qualifying_before[:10]}
    
    sorted_qual = sorted(qualified.items(), key=lambda x: x[1]['hit_count'], reverse=True)
    sorted_qual_before = sorted(qualified_before.items(), key=lambda x: x[1]['hit_count'], reverse=True)
    common_numbers = set(qualified.keys()).intersection(set(qualified_before.keys()))
    
    return jsonify({
        'algorithm': '3DP-AP',
        'db_mode': get_db_mode(),
        'seed_number': seed_number,
        'seed_date': seed_date_str,
        'normalized_seed': normalized_seed,
        'state': state,
        'game_type': 'pick5',
        'days_threshold': days_threshold,
        'pairs_3dp': pairs_3dp,
        'total_3dp_candidates': len(candidates),
        'seed_historical_hits': len(seed_hits),
        'seed_history': [{'date': h['date'].strftime('%Y-%m-%d'), 'value': h['value'], 'date_diff': h['date_diff']} for h in seed_hits],
        'qualified_count': len(qualified),
        'predictions': [{'number': num, **info} for num, info in sorted_qual],
        'all_numbers': sorted([num for num, _ in sorted_qual]),
        'qualified_before_count': len(qualified_before),
        'predictions_before': [{'number': num, **info} for num, info in sorted_qual_before],
        'all_numbers_before': sorted([num for num, _ in sorted_qual_before]),
        'common_count': len(common_numbers),
        'common_numbers': sorted(list(common_numbers))
    })

@app.route('/predictions/pick5', strict_slashes=False)
def predictions_pick5_page():
    return render_template('predictions_unified.html')

@app.route('/predictions/unified', strict_slashes=False)
def predictions_unified_page():
    return render_template('predictions_unified.html')


# =============================================================================
# UNIFIED DP-AP PREDICTION ENDPOINT
# =============================================================================

@app.route('/api/prediction/unified-dp-ap', methods=['POST'])
def unified_dp_ap_prediction():
    """
    Unified DP-AP (Digit Pair - All Possibles) Prediction Algorithm.
    
    Supports Pick2-Pick5 with configurable pair sizes:
    - Pick2: 1DP
    - Pick3: 1DP, 2DP
    - Pick4: 1DP, 2DP, 3DP
    - Pick5: 1DP, 2DP, 3DP, 4DP
    """
    collection = get_collection()
    data = request.json
    
    state = data.get('state', 'Florida')
    game_type = data.get('game_type', 'pick4').lower()
    seed_number = data.get('seed_number', '')
    seed_date = data.get('seed_date', datetime.now().strftime('%Y-%m-%d'))
    pair_size = int(data.get('pair_size', 2))
    days_threshold = int(data.get('days_threshold', 30))
    min_hits = int(data.get('min_hits', 2))
    
    # Game configuration
    game_config = {
        'pick2': {'digits': 2, 'valid_pairs': [1]},
        'pick3': {'digits': 3, 'valid_pairs': [1, 2]},
        'pick4': {'digits': 4, 'valid_pairs': [1, 2, 3]},
        'pick5': {'digits': 5, 'valid_pairs': [1, 2, 3, 4]},
    }
    
    config = game_config.get(game_type)
    if not config:
        return jsonify({'error': f'Invalid game type: {game_type}'}), 400
    
    num_digits = config['digits']
    
    # Validate pair size
    if pair_size not in config['valid_pairs']:
        pair_size = config['valid_pairs'][-1]  # Use largest valid pair
    
    # Validate seed number
    seed_number = seed_number.replace('-', '').replace(' ', '')
    if len(seed_number) != num_digits:
        return jsonify({'error': f'Seed must be {num_digits} digits for {game_type}'}), 400
    
    # Get games for this state
    games = get_games_for_prediction(state, game_type)
    if not games:
        return jsonify({'error': f'No {game_type} games found for {state}', 'db_mode': get_db_mode()}), 404
    
    # Fetch all draws
    query = {'state_name': state, 'game_name': {'$in': games}}
    all_draws = list(collection.find(query).sort('date', 1))
    
    # Parse seed date
    try:
        seed_dt = datetime.strptime(seed_date, '%Y-%m-%d')
    except:
        seed_dt = datetime.now()
    
    # Normalize seed
    seed_norm = get_sorted_value(list(seed_number)).replace('-', '')
    
    # Get digit pairs using unified function
    pairs = get_dp_pairs(seed_number, pair_size)
    
    # Generate candidates
    candidates = generate_dp_candidates(pairs, num_digits)
    
    # Build draws index by normalized value
    draws_by_norm = {}
    for d in all_draws:
        nums = parse_numbers(d.get('numbers', '[]'))
        if len(nums) == num_digits:
            norm = get_sorted_value(nums).replace('-', '')
            if norm not in draws_by_norm:
                draws_by_norm[norm] = []
            draws_by_norm[norm].append({
                'date': d['date'],
                'value': '-'.join(nums),
                'tod': d.get('tod', '')
            })
    
    # Get seed history (when this normalized number hit before seed date)
    seed_history = []
    for h in draws_by_norm.get(seed_norm, []):
        if h['date'] < seed_dt:
            diff = (seed_dt - h['date']).days
            seed_history.append({
                'date': h['date'].strftime('%Y-%m-%d'),
                'value': h['value'],
                'date_diff': diff
            })
    seed_history = sorted(seed_history, key=lambda x: x['date_diff'])
    
    # Find candidates that hit AFTER seed's historical occurrences
    qualified_after = {}
    for cand in candidates:
        cand_norm = get_sorted_value(list(cand)).replace('-', '')
        cand_hits = draws_by_norm.get(cand_norm, [])
        
        for sh in seed_history:
            sh_date = datetime.strptime(sh['date'], '%Y-%m-%d')
            for ch in cand_hits:
                days_diff = (ch['date'] - sh_date).days
                if 0 < days_diff <= days_threshold:
                    if cand not in qualified_after:
                        qualified_after[cand] = {'normalized': cand_norm, 'hit_count': 0, 'hits': []}
                    qualified_after[cand]['hit_count'] += 1
                    qualified_after[cand]['hits'].append({
                        'date': ch['date'].strftime('%Y-%m-%d'),
                        'value': ch['value'],
                        'days_after': days_diff
                    })
    
    # Find candidates that hit BEFORE seed's historical occurrences
    qualified_before = {}
    for cand in candidates:
        cand_norm = get_sorted_value(list(cand)).replace('-', '')
        cand_hits = draws_by_norm.get(cand_norm, [])
        
        for sh in seed_history:
            sh_date = datetime.strptime(sh['date'], '%Y-%m-%d')
            for ch in cand_hits:
                days_diff = (ch['date'] - sh_date).days
                if -days_threshold <= days_diff < 0:
                    if cand not in qualified_before:
                        qualified_before[cand] = {'normalized': cand_norm, 'hit_count': 0, 'hits': []}
                    qualified_before[cand]['hit_count'] += 1
                    qualified_before[cand]['hits'].append({
                        'date': ch['date'].strftime('%Y-%m-%d'),
                        'value': ch['value'],
                        'days_before': abs(days_diff)
                    })
    
    # Filter by min hits
    qualified_after = {k: v for k, v in qualified_after.items() if v['hit_count'] >= min_hits}
    qualified_before = {k: v for k, v in qualified_before.items() if v['hit_count'] >= min_hits}
    
    # Find common (in both after and before)
    common_numbers = sorted(set(qualified_after.keys()) & set(qualified_before.keys()))
    
    # Sort by hit count
    sorted_after = sorted(qualified_after.items(), key=lambda x: x[1]['hit_count'], reverse=True)
    sorted_before = sorted(qualified_before.items(), key=lambda x: x[1]['hit_count'], reverse=True)
    
    return jsonify({
        'state': state,
        'game_type': game_type,
        'seed_number': seed_number,
        'seed_date': seed_date,
        'normalized_seed': seed_norm,
        'pair_size': pair_size,
        'pairs': pairs,
        'total_candidates': len(candidates),
        'seed_historical_hits': len(seed_history),
        'seed_history': seed_history[:20],
        'qualified_count': len(qualified_after),
        'qualified_before_count': len(qualified_before),
        'common_count': len(common_numbers),
        'common_numbers': common_numbers,
        'predictions': [{'number': num, **info} for num, info in sorted_after[:50]],
        'predictions_before': [{'number': num, **info} for num, info in sorted_before[:50]],
        'all_numbers': sorted(qualified_after.keys()),
        'all_numbers_before': sorted(qualified_before.keys()),
        'db_mode': get_db_mode()
    })


# =============================================================================
# UNIFIED GAME-SPECIFIC API ROUTES
# =============================================================================

@app.route('/api/prediction/<game_type>/states')
def get_prediction_states_by_game(game_type):
    """
    Get states that have the specified game type.
    Supports: pick2, pick3, pick4, pick5
    """
    collection = get_collection()
    all_states = collection.distinct('state_name')
    
    # Game patterns for each type
    game_patterns = {
        'pick2': ['pick 2', 'pick2', 'daily 2', 'daily2', 'play 2', 'play2'],
        'pick3': ['pick 3', 'pick3', 'daily 3', 'daily3', 'cash 3', 'cash3', 'play 3', 'play3'],
        'pick4': ['pick 4', 'pick4', 'daily 4', 'daily4', 'cash 4', 'cash4', 'win 4', 'win4', 'play 4', 'play4'],
        'pick5': ['pick 5', 'pick5', 'daily 5', 'daily5', 'cash 5', 'cash5', 'play 5', 'play5', 'georgia five'],
    }
    
    patterns = game_patterns.get(game_type.lower(), [])
    if not patterns:
        return jsonify({'error': f'Invalid game type: {game_type}'}), 400
    
    # Filter to states that have this game type
    matching_states = []
    for state in all_states:
        if not state:
            continue
        games = collection.distinct('game_name', {'state_name': state})
        for g in games:
            gl = g.lower()
            if any(p in gl for p in patterns):
                matching_states.append(state)
                break
    
    return jsonify(sorted(matching_states))


# =============================================================================
# PICK5 SPECIFIC API ROUTES (backwards compatibility)
# =============================================================================

@app.route('/api/prediction/pick5/states')
def get_prediction_pick5_states():
    """Get states that have Pick 5 games."""
    return get_prediction_states_by_game('pick5')

@app.route('/api/prediction/pick5/games/<state>')
def get_prediction_pick5_games(state):
    """Get Pick 5 games for a state."""
    collection = get_collection()
    games = collection.distinct('game_name', {'state_name': state})
    
    pick5_games = []
    for g in games:
        gl = g.lower()
        if any(x in gl for x in ['pick 5', 'pick5', 'daily 5', 'daily5', 'cash 5', 'cash5']):
            pick5_games.append({'id': g, 'name': g})
    
    return jsonify(pick5_games)

@app.route('/api/prediction/pick5/latest/<state>')
def get_latest_pick5_draw(state):
    """Get the latest Pick 5 draw for a state."""
    collection = get_collection()
    games = get_games_for_prediction(state, 'pick5')
    if not games:
        return jsonify({'error': 'No pick5 games found', 'db_mode': get_db_mode()}), 404
    
    query = {'state_name': state, 'game_name': {'$in': games}}
    latest = collection.find_one(query, sort=[('date', -1)])
    
    if latest:
        nums = parse_numbers(latest.get('numbers', '[]'))
        return jsonify({
            'date': latest['date'].strftime('%Y-%m-%d'),
            'value': '-'.join(nums),
            'normalized': get_sorted_value(nums),
            'game': latest['game_name'],
            'tod': latest.get('tod', ''),
            'db_mode': get_db_mode()
        })
    return jsonify({'error': 'No draws found', 'db_mode': get_db_mode()}), 404

@app.route('/api/prediction/pick5/draw-by-date/<state>/<draw_date>')
def get_pick5_draw_by_date(state, draw_date):
    """Get Pick 5 draw for a specific date."""
    collection = get_collection()
    games = get_games_for_prediction(state, 'pick5')
    if not games:
        return jsonify({'error': 'No pick5 games found', 'db_mode': get_db_mode()}), 404
    
    try:
        date_obj = datetime.strptime(draw_date, '%Y-%m-%d')
    except:
        return jsonify({'error': 'Invalid date format'}), 400
    
    query = {
        'state_name': state,
        'game_name': {'$in': games},
        'date': {'$gte': date_obj, '$lt': date_obj + timedelta(days=1)}
    }
    
    tod = request.args.get('tod', '')
    draws = list(collection.find(query))
    
    if not draws:
        return jsonify({'error': f'No draw found for {draw_date}', 'db_mode': get_db_mode()}), 404
    
    if tod:
        filtered = [d for d in draws if d.get('tod', '').lower() == tod.lower()]
        if filtered:
            draws = filtered
    
    draw = draws[0]
    nums = parse_numbers(draw.get('numbers', '[]'))
    
    return jsonify({
        'date': draw['date'].strftime('%Y-%m-%d'),
        'value': '-'.join(nums),
        'normalized': get_sorted_value(nums),
        'game': draw['game_name'],
        'tod': draw.get('tod', ''),
        'db_mode': get_db_mode()
    })



# =============================================================================
# EFFICACY REPORT ROUTES
# =============================================================================

@app.route('/report/efficacy')
def efficacy_report_page():
    return render_template('efficacy_report_unified.html')

@app.route('/report/efficacy-unified')
def efficacy_report_unified_page():
    return render_template('efficacy_report_unified.html')

@app.route('/report/efficacy-pick5')
def efficacy_report_pick5_page():
    return render_template('efficacy_report_unified.html')


# =============================================================================
# QUERY COST ESTIMATION & BACKGROUND JOBS API
# =============================================================================

@app.route('/api/query/estimate-cost', methods=['POST'])
def estimate_cost_endpoint():
    """
    Estimate the cost and time for a query before running it.
    Returns whether the query is heavy/chargeable and offers options.
    """
    data = request.json
    query_type = data.get('query_type', 'efficacy_report')
    params = data.get('params', {})
    
    estimate = estimate_query_cost(query_type, params)
    
    if estimate['is_heavy'] or estimate['is_chargeable']:
        return jsonify({
            'requires_confirmation': True,
            'estimate': estimate,
            'message': _build_cost_message(estimate),
            'options': [
                {'action': 'cancel', 'label': 'Cancel', 'icon': '❌'},
                {'action': 'background', 'label': 'Run in Background', 'icon': '📧', 'requires_email': True},
                {'action': 'proceed', 'label': f"Run Now{' ($' + str(estimate['estimated_cost']) + ')' if estimate['is_chargeable'] else ''}", 'icon': '▶️'}
            ]
        })
    
    return jsonify({
        'requires_confirmation': False,
        'estimate': estimate,
        'message': 'Query is within free tier limits'
    })


@app.route('/api/query/background-job', methods=['POST'])
def create_background_job_endpoint():
    """
    Create a background job for a heavy query.
    User will be notified by email when complete.
    """
    data = request.json
    job_type = data.get('job_type', 'efficacy_report')
    params = data.get('params', {})
    user_email = data.get('email', '')
    
    if not user_email or '@' not in user_email:
        return jsonify({'error': 'Valid email required for background jobs'}), 400
    
    job_id = create_background_job(job_type, params, user_email)
    
    # In production, this would queue the job to Celery/Redis
    # For now, just acknowledge the request
    
    return jsonify({
        'success': True,
        'job_id': job_id,
        'status': 'queued',
        'message': f'Job queued. Results will be sent to {user_email} when complete.',
        'estimated_time': estimate_query_cost(job_type, params).get('estimated_time_seconds', 30)
    })


@app.route('/api/query/job-status/<job_id>')
def get_job_status_endpoint(job_id):
    """Get the status of a background job."""
    job = get_job_status(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify(job)


@app.route('/api/query/charge', methods=['POST'])
def charge_for_query():
    """
    Process payment for a chargeable query.
    In production, this would integrate with Stripe.
    """
    data = request.json
    amount = data.get('amount', 0)
    query_type = data.get('query_type', '')
    user_id = data.get('user_id', 'anonymous')
    
    # Mock charge - in production use Stripe
    charge_id = hashlib.md5(f"{user_id}{amount}{datetime.now().isoformat()}".encode()).hexdigest()[:10]
    
    return jsonify({
        'success': True,
        'charge_id': f'ch_{charge_id}',
        'amount': amount,
        'message': f'Charged ${amount:.4f} for {query_type}'
    })


def _build_cost_message(estimate):
    """Build a human-readable message about query cost."""
    parts = []
    
    if estimate['estimated_time_seconds'] > 15:
        parts.append(f"⏱️ This query may take ~{int(estimate['estimated_time_seconds'])} seconds.")
    
    if estimate['is_chargeable']:
        parts.append(f"💰 Cost: ${estimate['estimated_cost']:.4f}")
    
    if estimate.get('warnings'):
        parts.append("⚠️ " + " | ".join(estimate['warnings']))
    
    if estimate['recommendation'] == 'background':
        parts.append("💡 We recommend running this in the background.")
    
    return " ".join(parts) if parts else "Query ready to run."

@app.route('/api/prediction/efficacy-report', methods=['POST'])
def efficacy_report():
    """
    Unified DP AP (Digit Pair - All Possibles) Efficacy Report
    
    Supports Pick2 through Pick5 with dynamic pair sizes:
    - Pick2: 1DP
    - Pick3: 1DP, 2DP
    - Pick4: 1DP, 2DP, 3DP
    - Pick5: 1DP, 2DP, 3DP, 4DP
    
    Rule: pair_size must be < num_digits
    """
    collection = get_collection()
    data = request.json
    state = data.get('state', 'California')
    start_date = datetime.strptime(data.get('start_date', '2026-01-01'), '%Y-%m-%d')
    end_date = datetime.strptime(data.get('end_date', '2026-01-31'), '%Y-%m-%d')
    days_threshold = int(data.get('days_threshold', 30))
    hit_window = int(data.get('hit_window', 10))
    game_type = data.get('game_type', 'pick4').lower()
    pair_size = int(data.get('pair_size', 0))  # 0 means use default
    
    # Unified game configuration for Pick2-Pick5
    # Valid pairs: 1 to (digits-1) - you can't match the whole number
    game_config = {
        'pick2': {'digits': 2, 'valid_pairs': [1], 'default_pair': 1},
        'pick3': {'digits': 3, 'valid_pairs': [1, 2], 'default_pair': 2},
        'pick4': {'digits': 4, 'valid_pairs': [1, 2, 3], 'default_pair': 2},
        'pick5': {'digits': 5, 'valid_pairs': [1, 2, 3, 4], 'default_pair': 3},
    }
    
    config = game_config.get(game_type)
    if not config:
        return jsonify({'error': f'Invalid game type: {game_type}. Supported: pick2, pick3, pick4, pick5', 'db_mode': get_db_mode()}), 400
    
    num_digits = config['digits']
    
    # Use default pair size if not specified or invalid
    if pair_size not in config['valid_pairs']:
        pair_size = config['default_pair']
    
    games = get_games_for_prediction(state, game_type)
    if not games:
        return jsonify({'error': f'No {game_type} games found for {state}', 'db_mode': get_db_mode()}), 404
    
    query = {'state_name': state, 'game_name': {'$in': games}}
    all_draws = list(collection.find(query).sort('date', 1))
    
    # Build draws index by normalized value
    draws_by_norm = {}
    for d in all_draws:
        nums = parse_numbers(d.get('numbers', '[]'))
        if len(nums) == num_digits:
            norm = get_sorted_value(nums).replace('-', '')
            if norm not in draws_by_norm:
                draws_by_norm[norm] = []
            draws_by_norm[norm].append({
                'date': d['date'],
                'value': '-'.join(nums),
                'tod': d.get('tod', '')
            })
    
    # Get seeds in date range
    seeds_in_range = [d for d in all_draws 
                      if start_date <= d['date'] <= end_date 
                      and len(parse_numbers(d.get('numbers', '[]'))) == num_digits]
    
    results = []
    total_common = 0
    total_hits_within_window = 0
    
    for seed_draw in seeds_in_range:
        seed_nums = parse_numbers(seed_draw.get('numbers', '[]'))
        seed_norm = get_sorted_value(seed_nums).replace('-', '')
        seed_date = seed_draw['date']
        seed_value = '-'.join(seed_nums)
        
        # Get pairs using unified function
        pairs = get_dp_pairs(seed_norm, pair_size)
        candidates = generate_dp_candidates(pairs, num_digits)
        
        seed_history = [h for h in draws_by_norm.get(seed_norm, []) if h['date'] < seed_date]
        
        if not seed_history:
            continue
        
        # Find candidates that hit AFTER seed's historical hits
        qualified_after = set()
        for cand in candidates:
            cand_norm = get_sorted_value(list(cand)).replace('-', '')
            cand_hits = draws_by_norm.get(cand_norm, [])
            for sh in seed_history:
                for ch in cand_hits:
                    days_diff = (ch['date'] - sh['date']).days
                    if 0 < days_diff <= days_threshold:
                        qualified_after.add(cand)
                        break
        
        # Find candidates that hit BEFORE seed's historical hits
        qualified_before = set()
        for cand in candidates:
            cand_norm = get_sorted_value(list(cand)).replace('-', '')
            cand_hits = draws_by_norm.get(cand_norm, [])
            for sh in seed_history:
                for ch in cand_hits:
                    days_diff = (ch['date'] - sh['date']).days
                    if -days_threshold <= days_diff < 0:
                        qualified_before.add(cand)
                        break
        
        # Common candidates (hit both before AND after seed historically)
        common = qualified_after.intersection(qualified_before)
        
        if not common:
            common = set()  # Continue anyway to capture pair matches
        
        # Check if common candidates actually hit within window of current seed
        hits_within_window = []
        for num in common:
            num_norm = get_sorted_value(list(num)).replace('-', '')
            num_hits = draws_by_norm.get(num_norm, [])
            for h in num_hits:
                days_diff = (h['date'] - seed_date).days
                if -hit_window <= days_diff <= hit_window and days_diff != 0:
                    hits_within_window.append({
                        'number': num,
                        'hit_date': h['date'].strftime('%Y-%m-%d'),
                        'hit_value': h['value'],
                        'days_from_seed': days_diff,
                        'direction': 'AFTER' if days_diff > 0 else 'BEFORE',
                        'source': 'COMMON'
                    })
                    break
        
        # NEW: Find ALL candidates (not just common) that hit within window
        # This captures same-day hits and other pair matches regardless of historical pattern
        pair_hits_in_window = []
        for cand in candidates:
            cand_norm = get_sorted_value(list(cand)).replace('-', '')
            cand_hits = draws_by_norm.get(cand_norm, [])
            for h in cand_hits:
                days_diff = (h['date'] - seed_date).days
                # Include same day (days_diff == 0) but different TOD, and within window
                if -hit_window <= days_diff <= hit_window:
                    # Skip if it's the exact same draw (same date, same value)
                    if days_diff == 0 and cand_norm == seed_norm:
                        continue
                    pair_hits_in_window.append({
                        'number': cand,
                        'hit_date': h['date'].strftime('%Y-%m-%d'),
                        'hit_value': h['value'],
                        'days_from_seed': days_diff,
                        'direction': 'SAME DAY' if days_diff == 0 else ('AFTER' if days_diff > 0 else 'BEFORE'),
                        'source': 'COMMON' if cand in common else 'PAIR MATCH',
                        'tod': h.get('tod', '')
                    })
                    break
        
        total_common += len(common) if common else 0
        total_hits_within_window += len(hits_within_window)
        
        # Only add to results if there are pair hits (even if no common)
        if pair_hits_in_window or common:
            results.append({
                'seed_date': seed_date.strftime('%Y-%m-%d'),
                'seed_value': seed_value,
                'seed_norm': seed_norm,
                'seed_tod': seed_draw.get('tod', ''),
                'pairs': pairs,
                'total_candidates': len(candidates),
                'common_count': len(common) if common else 0,
                'hits_within_window': len(hits_within_window),
                'pair_hits_in_window': len(pair_hits_in_window),
                'hit_rate': round(len(hits_within_window) / len(common) * 100, 1) if common else 0,
                'hits_detail': hits_within_window,
                'all_pair_hits': pair_hits_in_window  # NEW: All pair matches in window
            })
    
    overall_rate = round(total_hits_within_window / total_common * 100, 1) if total_common > 0 else 0
    
    # Calculate pair hit stats
    total_pair_hits = sum(r.get('pair_hits_in_window', 0) for r in results)
    
    # Algorithm name based on pair size
    algo_name = f'{pair_size}DP-AP'
    
    return jsonify({
        'state': state,
        'game_type': game_type,
        'algorithm': algo_name,
        'pair_size': pair_size,
        'num_digits': num_digits,
        'valid_pair_sizes': config['valid_pairs'],
        'db_mode': get_db_mode(),
        'date_range': f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}",
        'days_threshold': days_threshold,
        'hit_window': hit_window,
        'total_seeds_analyzed': len(results),
        'total_common_predicted': total_common,
        'total_hits_within_window': total_hits_within_window,
        'total_pair_hits_in_window': total_pair_hits,
        'overall_hit_rate': overall_rate,
        'results': results
    })


@app.route('/api/prediction/dp-options/<game_type>')
def get_dp_options(game_type):
    """
    Get available digit pair options for a game type.
    
    Unified for Pick2-Pick5:
    - Pick2: 1DP only
    - Pick3: 1DP, 2DP
    - Pick4: 1DP, 2DP, 3DP
    - Pick5: 1DP, 2DP, 3DP, 4DP
    
    Rule: pair_size must be < num_digits
    """
    # Define options with descriptions and candidate counts
    dp_descriptions = {
        1: {'label': '1DP - Single Digits', 'desc': 'Match any single digit', 'coverage': 'High'},
        2: {'label': '2DP - 2-Digit Pairs', 'desc': 'Match pairs of 2 digits', 'coverage': 'Medium'},
        3: {'label': '3DP - 3-Digit Pairs', 'desc': 'Match pairs of 3 digits', 'coverage': 'Low'},
        4: {'label': '4DP - 4-Digit Pairs', 'desc': 'Match pairs of 4 digits', 'coverage': 'Very Low'},
    }
    
    # Estimated candidate counts for each game/pair combo
    candidate_estimates = {
        'pick2': {1: 10},
        'pick3': {1: 220, 2: 55},
        'pick4': {1: 715, 2: 330, 3: 120},
        'pick5': {1: 2002, 2: 715, 3: 252, 4: 126},
    }
    
    # Default pair sizes (balanced between coverage and precision)
    defaults = {
        'pick2': 1,
        'pick3': 2,
        'pick4': 2,
        'pick5': 3,
    }
    
    game = game_type.lower()
    
    # Get number of digits for this game
    num_digits = {'pick2': 2, 'pick3': 3, 'pick4': 4, 'pick5': 5}.get(game)
    
    if not num_digits:
        return jsonify({'error': f'Invalid game type: {game_type}. Supported: pick2, pick3, pick4, pick5'}), 400
    
    # Valid pairs are 1 to (digits-1)
    valid_pairs = list(range(1, num_digits))
    
    options = []
    for size in valid_pairs:
        info = dp_descriptions.get(size, {})
        est_candidates = candidate_estimates.get(game, {}).get(size, 'N/A')
        options.append({
            'size': size,
            'label': info.get('label', f'{size}DP'),
            'description': info.get('desc', f'Match {size}-digit combinations'),
            'coverage': info.get('coverage', 'Unknown'),
            'estimated_candidates': est_candidates
        })
    
    return jsonify({
        'game_type': game,
        'num_digits': num_digits,
        'options': options,
        'default': defaults.get(game, valid_pairs[-1])
    })

@app.route('/api/prediction/efficacy-report-all-states', methods=['POST'])
def efficacy_report_all_states():
    """Generate efficacy report across all states"""
    return efficacy_report()

# =============================================================================
# RBTL ALGORITHM - Repeat By The Lookup
# =============================================================================

@app.route('/rbtl')
def rbtl_page():
    """Page for RBTL algorithm - historical pattern finder."""
    return render_template('rbtl_algorithm.html')


@app.route('/api/draws/recent', methods=['POST'])
def get_recent_draws():
    """
    Get recent actual draws for seed selection UI.
    Returns raw draws (value, actual/normalized, date, TOD) — no analysis.
    
    Request body:
        state, game_type, start_date, end_date
    
    Returns:
        draws: [{date, value, actual, tod}, ...]
    """
    collection = get_collection()
    data = request.json

    state = data.get('state', 'Florida')
    game_type = data.get('game_type', 'pick4').lower()
    start_date = datetime.strptime(data.get('start_date', '2026-01-01'), '%Y-%m-%d')
    end_date = datetime.strptime(data.get('end_date', '2026-01-07'), '%Y-%m-%d')

    num_digits = {'pick2': 2, 'pick3': 3, 'pick4': 4, 'pick5': 5}.get(game_type, 4)
    games = get_games_for_prediction(state, game_type)
    if not games:
        return jsonify({'error': f'No {game_type} games found for {state}'}), 404

    query = {
        'state_name': state,
        'game_name': {'$in': games},
        'date': {'$gte': start_date, '$lte': end_date}
    }

    all_draws = list(collection.find(query).sort('date', -1))

    draws = []
    for d in all_draws:
        nums = d.get('winning_numbers', d.get('numbers', []))
        # Handle JSON string from MongoOptimizedCursor adapter
        if isinstance(nums, str):
            try:
                nums = json.loads(nums)
            except (json.JSONDecodeError, ValueError):
                nums = list(nums.replace(' ', '').replace('-', ''))
        nums = [str(n) for n in nums][:num_digits]
        if len(nums) != num_digits:
            continue
        value = ''.join(nums)
        actual = ''.join(sorted(nums))
        tod = d.get('tod', d.get('draw_time', ''))
        if not tod:
            gn = d.get('game_name', '').lower()
            if 'midday' in gn or 'mid-day' in gn or 'day' in gn:
                tod = 'Midday'
            elif 'evening' in gn or 'eve' in gn or 'night' in gn:
                tod = 'Evening'
            else:
                tod = ''
        draws.append({
            'date': d['date'].strftime('%Y-%m-%d'),
            'value': value,
            'actual': actual,
            'tod': tod
        })

    return jsonify({
        'state': state,
        'game_type': game_type,
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d'),
        'count': len(draws),
        'draws': draws
    })


@app.route('/api/rbtl/data-stats/<state>/<game_type>')
def rbtl_data_stats(state, game_type):
    """
    Get data statistics for admin display.
    Shows last draw date, total draws, and date range.
    """
    collection = get_collection()
    
    # Get number of digits for this game
    num_digits = {'pick2': 2, 'pick3': 3, 'pick4': 4, 'pick5': 5}.get(game_type.lower(), 4)
    
    # Get games for this state
    games = get_games_for_prediction(state, game_type.lower())
    if not games:
        return jsonify({'error': f'No {game_type} games found for {state}'}), 404
    
    # Query for this state/game
    query = {'state_name': state, 'game_name': {'$in': games}}
    
    # Get all draws and count them (works with adapter)
    all_draws = list(collection.find(query).sort('date', 1))
    total_draws = len(all_draws)
    
    if total_draws == 0:
        return jsonify({'error': 'No draws found'}), 404
    
    # First and last draw
    first_draw = all_draws[0]
    last_draw = all_draws[-1]
    
    return jsonify({
        'state': state,
        'game_type': game_type,
        'total_draws': total_draws,
        'first_draw_date': first_draw['date'].strftime('%Y-%m-%d'),
        'last_draw_date': last_draw['date'].strftime('%Y-%m-%d'),
        'games': games,
        'db_mode': get_db_mode()
    })

@app.route('/api/rbtl/analyze', methods=['POST'])
def rbtl_analyze():
    """
    RBTL (Repeat By The Lookup) Algorithm
    
    For each draw in the input date range:
    1. Get its normalized (Perm) value
    2. Find ALL historical dates when that Perm hit
    3. Calculate stats like digit sums, times drawn, repeat patterns
    
    Returns a table similar to MyLottoData's RBTL output.
    """
    collection = get_collection()
    data = request.json
    
    state = data.get('state', 'Florida')
    game_type = data.get('game_type', 'pick4').lower()
    start_date = datetime.strptime(data.get('start_date', '2026-01-01'), '%Y-%m-%d')
    end_date = datetime.strptime(data.get('end_date', '2026-01-07'), '%Y-%m-%d')
    draw_time = data.get('draw_time', '')  # Midday, Evening, or empty for all
    
    # Get number of digits for this game
    num_digits = {'pick2': 2, 'pick3': 3, 'pick4': 4, 'pick5': 5}.get(game_type, 4)
    
    # Get games for this state
    games = get_games_for_prediction(state, game_type)
    if not games:
        return jsonify({'error': f'No {game_type} games found for {state}'}), 404
    
    # Fetch ALL historical draws for this state/game
    query = {'state_name': state, 'game_name': {'$in': games}}
    all_draws = list(collection.find(query).sort('date', 1))
    
    # Build index by normalized value (actual = normalized/sorted)
    draws_by_actual = {}
    actual_times_drawn = {}  # Count total times each actual was drawn
    
    for d in all_draws:
        nums = parse_numbers(d.get('numbers', '[]'))
        if len(nums) != num_digits:
            continue
        
        actual = get_sorted_value(nums).replace('-', '')
        
        if actual not in draws_by_actual:
            draws_by_actual[actual] = []
            actual_times_drawn[actual] = 0
        
        actual_times_drawn[actual] += 1
        draws_by_actual[actual].append({
            'date': d['date'],
            'value': ''.join(nums),
            'tod': d.get('tod', '')
        })
    
    # Get seed draws from input date range
    seed_draws = []
    for d in all_draws:
        if start_date <= d['date'] <= end_date:
            nums = parse_numbers(d.get('numbers', '[]'))
            if len(nums) != num_digits:
                continue
            
            # Filter by draw time if specified
            if draw_time and d.get('tod', '').lower() != draw_time.lower():
                continue
            
            actual = get_sorted_value(nums).replace('-', '')
            seed_draws.append({
                'date': d['date'],
                'value': ''.join(nums),  # Original drawn value
                'actual': actual,         # Normalized/sorted
                'tod': d.get('tod', '')
            })
    
    if not seed_draws:
        return jsonify({'error': 'No draws found in the specified date range'}), 404
    
    # Collect past winners - use ORIGINAL values, not normalized
    past_winners_values = [s['value'] for s in seed_draws]
    past_winners_actuals = list(set(s['actual'] for s in seed_draws))
    
    # Build results - for each seed, find all historical occurrences
    results = []
    
    for seed in seed_draws:
        seed_actual = seed['actual']
        seed_value = seed['value']
        seed_date = seed['date']
        
        # Get all historical hits of this actual (normalized)
        historical_hits = draws_by_actual.get(seed_actual, [])
        
        for hist in historical_hits:
            # Calculate date difference from seed to historical hit
            date_diff = (hist['date'] - seed_date).days
            
            # Skip if it's the seed itself (date_diff == 0 AND same value)
            if date_diff == 0 and hist['value'] == seed_value:
                continue
            
            # Calculate digit sum
            digit_sum = sum(int(d) for d in hist['value'])
            
            # Calculate repeat count (how many times actual hit within 30 days of this date)
            repeat_count = 0
            for other in historical_hits:
                days_diff = abs((other['date'] - hist['date']).days)
                if 0 < days_diff <= 30:
                    repeat_count += 1
            
            results.append({
                'month': hist['date'].strftime('%Y-%m'),
                'date': hist['date'].strftime('%Y-%m-%d'),
                'date_diff': date_diff,
                'value': hist['value'],
                'actual': seed_actual,
                'seed_value': seed_value,  # Original seed value
                'input_date': seed_date.strftime('%Y-%m-%d'),
                'sums': digit_sum,
                'times_drawn': actual_times_drawn.get(seed_actual, 0),
                'repeat_count': repeat_count,
                'tod': hist.get('tod', '')
            })
    
    # Sort by input_date desc, then by date_diff (closest to 0 first)
    results.sort(key=lambda x: (x['input_date'], abs(x['date_diff'])), reverse=True)
    
    return jsonify({
        'state': state,
        'game_type': game_type,
        'date_range': f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}",
        'seed_count': len(seed_draws),
        'past_winners': past_winners_values,  # Original values
        'past_winners_actual': past_winners_actuals,  # Normalized
        'unique_perms': len(past_winners_actuals),
        'total_historical_matches': len(results),
        'results': results[:500],  # Limit to 500 rows
        'db_mode': get_db_mode()
    })


@app.route('/api/rbtl/backtest-v2', methods=['POST'])
def rbtl_backtest_v2():
    """
    TRUE RBTL Backtesting - Matches the original RBTL workflow:
    
    1. Get seeds from lookback period (+ optional same-day earlier TOD)
    2. For each seed, find ALL historical permutation matches (before seed period)
    3. For each historical hit, create a ±N day cluster window
    4. Merge overlapping clusters, rank by COUNT of seed hits
    5. From top clusters, pull ALL numbers drawn in those windows → candidates
    6. Check if target winners appear in candidates
    
    Key difference from v1: uses rolling ±N day windows instead of calendar months,
    and candidates are ALL draws from hot clusters (not DP-pair filtered).
    """
    collection = get_collection()
    data = request.json
    
    state = data.get('state', 'Florida')
    game_type = data.get('game_type', 'pick4').lower()
    target_date = datetime.strptime(data.get('target_date', '2019-09-15'), '%Y-%m-%d')
    target_tod = data.get('target_tod', '').lower()  # 'evening', 'midday', or ''
    lookback_days = data.get('lookback_days', 5)
    cluster_window = data.get('cluster_window', 30)  # ±N days (kept for future use)
    top_n_clusters = data.get('top_n_clusters', 0)  # 0 = use ALL qualifying months
    min_count = data.get('min_count', 3)  # Minimum seed hits per month (MLD default: >=3)
    grouping = data.get('grouping', 'monthly')  # monthly, cluster_year, cluster_15/30/60
    duplicates_only = data.get('duplicates_only', False)  # MLD mode: only keep numbers appearing 2+ times in any single group
    truth_table_seed = data.get('truth_table_seed', '')  # If set, intersect candidates with ±1 digit combos of this seed
    include_same_day = data.get('include_same_day', True)
    
    num_digits = {'pick2': 2, 'pick3': 3, 'pick4': 4, 'pick5': 5}.get(game_type, 4)
    
    # Get games for this state
    games = get_games_for_prediction(state, game_type)
    if not games:
        return jsonify({'error': f'No {game_type} games found for {state}'}), 404
    
    # Fetch ALL historical draws for this state/game
    query = {'state_name': state, 'game_name': {'$in': games}}
    all_draws_raw = list(collection.find(query).sort('date', 1))
    
    # Parse all draws into a clean list
    all_draws = []
    for d in all_draws_raw:
        nums = parse_numbers(d.get('numbers', '[]'))
        if len(nums) != num_digits:
            continue
        actual = get_sorted_value(nums).replace('-', '')
        all_draws.append({
            'date': d['date'],
            'value': ''.join(nums),
            'actual': actual,
            'tod': d.get('tod', ''),
            'game': d.get('game_name', '')
        })
    
    if not all_draws:
        return jsonify({'error': 'No draws found in database'}), 404
    
    # === STEP 1: Get seeds ===
    # lookback_days=0 means "single-draw mode" — use only the most recent draw
    # lookback_days=-1 means "mid & eve mode" — use both draws from previous day
    # lookback_days>0 means use draws from N days before target + same-day earlier TOD
    
    if lookback_days == 0:
        # Single-draw mode: find the most recent draw BEFORE the target
        start_date = target_date - timedelta(days=1)  # For display purposes
        end_date = target_date - timedelta(days=1)
    elif lookback_days == -1:
        # Mid & Eve mode: get both draws from the previous day
        start_date = target_date - timedelta(days=1)
        end_date = target_date - timedelta(days=1)
    else:
        start_date = target_date - timedelta(days=lookback_days)
        end_date = target_date - timedelta(days=1)
    
    # The data cutoff: NO data on or after the target draw should be used
    data_cutoff = target_date
    
    # TOD ordering for same-day inclusion
    tod_order = {
        'early morning': 1, 'early': 1, 'morning': 2,
        'midday': 3, 'mid-day': 3, 'noon': 3,
        'day': 4, 'afternoon': 4,
        'evening': 5, 'night': 6,
        'late night': 7, 'late': 7
    }
    target_tod_order = tod_order.get(target_tod, 99)
    
    seed_draws = []
    
    if lookback_days == -1:
        # Mid & Eve mode: grab BOTH Midday and Evening from the day before target
        prev_day = target_date - timedelta(days=1)
        for d in all_draws:
            draw_date = d['date']
            if hasattr(draw_date, 'tzinfo') and draw_date.tzinfo:
                draw_date = draw_date.replace(tzinfo=None)
            if draw_date.date() == prev_day.date():
                seed_draws.append(d)
        
        # Also include same-day earlier TOD if predicting Evening
        if include_same_day and target_tod:
            for d in all_draws:
                draw_date = d['date']
                if hasattr(draw_date, 'tzinfo') and draw_date.tzinfo:
                    draw_date = draw_date.replace(tzinfo=None)
                draw_tod = d['tod'].lower() if d['tod'] else ''
                draw_order = tod_order.get(draw_tod, 0)
                if draw_date.date() == target_date.date() and draw_order < target_tod_order:
                    seed_draws.append(d)
        
        if seed_draws:
            start_date = min(d['date'] if not (hasattr(d['date'], 'tzinfo') and d['date'].tzinfo) else d['date'].replace(tzinfo=None) for d in seed_draws)
            end_date = max(d['date'] if not (hasattr(d['date'], 'tzinfo') and d['date'].tzinfo) else d['date'].replace(tzinfo=None) for d in seed_draws)
    
    elif lookback_days == 0:
        # Single-draw mode: find the MOST RECENT draw before the target
        # This handles both directions:
        #   - Predicting Evening: grabs same-day Midday
        #   - Predicting Midday: grabs previous day's Evening (or latest)
        #   - Predicting All: grabs most recent draw before target date
        
        candidates_for_seed = []
        for d in all_draws:
            draw_date = d['date']
            if hasattr(draw_date, 'tzinfo') and draw_date.tzinfo:
                draw_date = draw_date.replace(tzinfo=None)
            draw_tod = d['tod'].lower() if d['tod'] else ''
            draw_order = tod_order.get(draw_tod, 0)
            
            # Same-day earlier TOD
            if draw_date.date() == target_date.date() and target_tod:
                if draw_order < target_tod_order:
                    candidates_for_seed.append((draw_date, draw_order, d))
            # Previous days
            elif draw_date.date() < target_date.date():
                candidates_for_seed.append((draw_date, draw_order, d))
        
        if candidates_for_seed:
            # Sort by date desc, then TOD desc — most recent first
            candidates_for_seed.sort(key=lambda x: (x[0], x[1]), reverse=True)
            # Take just the most recent draw
            seed_draws = [candidates_for_seed[0][2]]
            start_date = candidates_for_seed[0][0]
            end_date = candidates_for_seed[0][0]
    else:
        # Normal lookback mode
        for d in all_draws:
            draw_date = d['date']
            if hasattr(draw_date, 'tzinfo') and draw_date.tzinfo:
                draw_date = draw_date.replace(tzinfo=None)
            draw_tod = d['tod'].lower() if d['tod'] else ''
            
            # Draws from lookback period
            if start_date <= draw_date <= end_date:
                seed_draws.append(d)
            
            # Same-day earlier TOD draws
            elif include_same_day and draw_date.date() == target_date.date():
                draw_order = tod_order.get(draw_tod, 0)
                if target_tod and draw_order < target_tod_order:
                    seed_draws.append(d)
    
    if not seed_draws:
        return jsonify({'error': 'No seed draws found in lookback period'}), 404
    
    seed_actuals = set(s['actual'] for s in seed_draws)
    
    # The latest seed date — ALL historical searches must be before this
    latest_seed_date = max(d['date'] for d in seed_draws)
    if hasattr(latest_seed_date, 'tzinfo') and latest_seed_date.tzinfo:
        latest_seed_date = latest_seed_date.replace(tzinfo=None)
    
    # === STEP 2: Find all historical permutation matches (before latest seed) ===
    # Build index of all draws by normalized value
    draws_by_actual = {}
    draws_by_date = {}  # date -> list of draws (for pulling cluster candidates)
    
    for d in all_draws:
        actual = d['actual']
        if actual not in draws_by_actual:
            draws_by_actual[actual] = []
        draws_by_actual[actual].append(d)
        
        date_key = d['date'].date() if hasattr(d['date'], 'date') else d['date']
        if date_key not in draws_by_date:
            draws_by_date[date_key] = []
        draws_by_date[date_key].append(d)
    
    historical_hits = []
    for seed in seed_draws:
        seed_actual = seed['actual']
        matches = draws_by_actual.get(seed_actual, [])
        for match in matches:
            match_date = match['date']
            if hasattr(match_date, 'tzinfo') and match_date.tzinfo:
                match_date = match_date.replace(tzinfo=None)
            # Only use hits STRICTLY BEFORE the latest seed draw
            if match_date.date() < latest_seed_date.date():
                historical_hits.append({
                    'date': match_date,
                    'value': match['value'],
                    'actual': match['actual'],
                    'tod': match['tod'],
                    'seed_actual': seed_actual,
                    'seed_value': seed['value']
                })
    
    if not historical_hits:
        return jsonify({'error': 'No historical matches found for seeds'}), 404
    
    # === STEP 3: Group historical hits ===
    # Grouping modes: 'monthly' (YYYY-MM), 'cluster_year' (YYYY), 'cluster_N' (±N day windows)
    historical_hits.sort(key=lambda x: x['date'])
    
    from collections import defaultdict
    hits_by_month = defaultdict(list)
    
    if grouping == 'cluster_year':
        # Group by calendar YEAR — merges months like 2013-03 + 2013-10
        for hit in historical_hits:
            year_key = hit['date'].strftime('%Y')
            hits_by_month[year_key].append(hit)
    elif grouping.startswith('cluster_') and grouping != 'cluster_year':
        # ±N day window clustering — merge nearby hits into rolling windows
        try:
            window_days = int(grouping.split('_')[1])
        except (IndexError, ValueError):
            window_days = 30
        
        # Build clusters: for each hit, create a window and merge overlapping ones
        if historical_hits:
            from datetime import timedelta as _td
            sorted_hits = sorted(historical_hits, key=lambda h: h['date'])
            clusters = []  # list of (start_date, end_date, [hits])
            
            for hit in sorted_hits:
                hit_date = hit['date']
                if hasattr(hit_date, 'date'):
                    hit_date_d = hit_date.date()
                else:
                    hit_date_d = hit_date
                
                win_start = hit_date_d - _td(days=window_days)
                win_end = hit_date_d + _td(days=window_days)
                
                # Try to merge into existing cluster
                merged = False
                for ci, (cs, ce, ch) in enumerate(clusters):
                    if win_start <= ce and win_end >= cs:
                        clusters[ci] = (min(cs, win_start), max(ce, win_end), ch + [hit])
                        merged = True
                        break
                
                if not merged:
                    clusters.append((win_start, win_end, [hit]))
            
            # Merge any clusters that now overlap after expansion
            changed = True
            while changed:
                changed = False
                new_clusters = []
                used = set()
                for i in range(len(clusters)):
                    if i in used:
                        continue
                    cs, ce, ch = clusters[i]
                    for j in range(i + 1, len(clusters)):
                        if j in used:
                            continue
                        cs2, ce2, ch2 = clusters[j]
                        if cs <= ce2 and ce >= cs2:
                            cs = min(cs, cs2)
                            ce = max(ce, ce2)
                            ch = ch + ch2
                            used.add(j)
                            changed = True
                    new_clusters.append((cs, ce, ch))
                    used.add(i)
                clusters = new_clusters
            
            for cs, ce, ch in clusters:
                cluster_key = f"{cs.strftime('%Y-%m-%d')} \u2192 {ce.strftime('%Y-%m-%d')}"
                hits_by_month[cluster_key] = ch
    else:
        # Default: group by calendar month (YYYY-MM)
        for hit in historical_hits:
            month_key = hit['date'].strftime('%Y-%m')
            hits_by_month[month_key].append(hit)
    
    # === STEP 4: Rank months by COUNT of seed hits (exactly like MLD "Count" column) ===
    hot_months = []
    for month, hits in hits_by_month.items():
        seed_norms_in_month = list(set(h['seed_actual'] for h in hits))
        seed_values_in_month = list(set(h['seed_value'] for h in hits))
        input_values = list(set(h['value'] for h in hits))
        hot_months.append({
            'month': month,
            'count': len(hits),  # Total seed permutation matches (MLD "Count" column)
            'unique_seeds': len(seed_norms_in_month),
            'seed_norms': seed_norms_in_month,
            'seed_values': seed_values_in_month,
            'input_values': input_values,  # The actual drawn values (MLD "Inputs" column)
        })
    
    # Sort by count descending (highest count = hottest month)
    hot_months.sort(key=lambda m: m['count'], reverse=True)
    
    # Filter by minimum count (MLD uses >=3 by default)
    qualified_months = [m for m in hot_months if m['count'] >= min_count]
    
    # Select months: use top N if specified, otherwise ALL qualifying months
    if top_n_clusters > 0:
        top_months = qualified_months[:top_n_clusters]
    else:
        top_months = qualified_months  # ALL months with count >= min_count
    
    # === STEP 5: Pull ALL numbers drawn in selected hot months ("Repeated" column) ===
    
    # Build index: group_key -> all draws in that group (before cutoff)
    draws_by_month = defaultdict(list)
    
    # For cluster_year: pre-compute which months had seed hits per year
    year_hit_months = {}
    if grouping == 'cluster_year':
        for year_key, year_hits in hits_by_month.items():
            hit_months = set()
            for h in year_hits:
                hit_months.add(h['date'].strftime('%Y-%m'))
            year_hit_months[year_key] = hit_months
    
    for d in all_draws:
        d_date = d['date']
        if hasattr(d_date, 'tzinfo') and d_date.tzinfo:
            d_date = d_date.replace(tzinfo=None)
        # Only include draws before the latest seed
        if d_date.date() < latest_seed_date.date():
            if grouping == 'cluster_year':
                # Only pull draws from SPECIFIC MONTHS that had seed hits
                # (not all draws from the year — matches MLD "Repeated" behavior)
                draw_year = d_date.strftime('%Y')
                draw_month = d_date.strftime('%Y-%m')
                hit_months = year_hit_months.get(draw_year, set())
                if draw_month in hit_months:
                    draws_by_month[draw_year].append(d)
            elif grouping.startswith('cluster_') and grouping != 'cluster_year':
                # For cluster mode: add draw to ALL clusters whose window contains this date
                draw_date = d_date.date() if hasattr(d_date, 'date') else d_date
                for cluster_key in hits_by_month:
                    try:
                        parts = cluster_key.split(' \u2192 ')
                        from datetime import datetime as _dt
                        cs = _dt.strptime(parts[0], '%Y-%m-%d').date()
                        ce = _dt.strptime(parts[1], '%Y-%m-%d').date()
                        if cs <= draw_date <= ce:
                            draws_by_month[cluster_key].append(d)
                    except (ValueError, IndexError):
                        pass
            else:
                month_key = d_date.strftime('%Y-%m')
                draws_by_month[month_key].append(d)
    
    candidate_info = {}  # actual -> {count, months, values, ...}
    
    for mi, month_info in enumerate(top_months):
        month_key = month_info['month']
        month_draws = draws_by_month.get(month_key, [])
        
        month_info['total_draws_in_month'] = len(month_draws)
        month_info['unique_actuals_in_month'] = len(set(d['actual'] for d in month_draws))
        
        # The "Repeated" numbers = all OTHER draws in this month
        # (excluding the seed matches themselves, which are the "Inputs")
        seed_actuals_in_month = set(month_info['seed_norms'])
        repeated_in_month = []
        
        for d in month_draws:
            actual = d['actual']
            
            # Track ALL draws (including seeds) as candidates
            if actual not in candidate_info:
                candidate_info[actual] = {
                    'actual': actual,
                    'month_count': 0,
                    'months': [],
                    'sample_values': set(),
                    'total_appearances': 0,
                    'actual_hits': len(draws_by_actual.get(actual, [])),  # Total times drawn in ALL history
                    'is_seed': actual in seed_actuals,
                    'draw_dates': []
                }
            if month_key not in candidate_info[actual]['months']:
                candidate_info[actual]['months'].append(month_key)
                candidate_info[actual]['month_count'] += 1
            candidate_info[actual]['sample_values'].add(d['value'])
            candidate_info[actual]['total_appearances'] += 1
            # Track actual draw date and closest seed proximity
            draw_date = d['date']
            if hasattr(draw_date, 'strftime'):
                draw_date_str = draw_date.strftime('%Y-%m-%d')
            else:
                draw_date_str = str(draw_date)
            # Calculate min days from any seed draw
            min_days_from_seed = None
            for seed in seed_draws:
                seed_date = seed['date']
                if hasattr(seed_date, 'date') and hasattr(draw_date, 'date'):
                    diff = abs((draw_date.date() if hasattr(draw_date, 'date') else draw_date) - (seed_date.date() if hasattr(seed_date, 'date') else seed_date)).days
                else:
                    diff = abs((draw_date - seed_date).days)
                if min_days_from_seed is None or diff < min_days_from_seed:
                    min_days_from_seed = diff
            candidate_info[actual]['draw_dates'].append({
                'date': draw_date_str,
                'month': month_key,
                'days_from_seed': min_days_from_seed,
                'value': d['value']
            })
            
            # Track repeated (non-seed) numbers separately
            if actual not in seed_actuals_in_month:
                repeated_in_month.append(d['value'])
        
        month_info['repeated_values'] = sorted(set(repeated_in_month))
        month_info['repeated_count'] = len(set(repeated_in_month))
    
    # Convert sets to lists for JSON
    for cand in candidate_info.values():
        cand['sample_values'] = sorted(list(cand['sample_values']))[:5]
    
    # === STEP 5a-FORWARD: Look-forward — did candidates appear AFTER seed date? ===
    look_forward_days = data.get('look_forward_days', 0)  # 0 = disabled
    if look_forward_days > 0:
        forward_cutoff = latest_seed_date + timedelta(days=look_forward_days)
        for cand in candidate_info.values():
            cand['forward_dates'] = []
            matches = draws_by_actual.get(cand['actual'], [])
            for match in matches:
                match_date = match['date']
                if hasattr(match_date, 'tzinfo') and match_date.tzinfo:
                    match_date = match_date.replace(tzinfo=None)
                if latest_seed_date.date() <= match_date.date() <= forward_cutoff.date():
                    days_after = (match_date.date() - latest_seed_date.date()).days
                    cand['forward_dates'].append({
                        'date': match_date.strftime('%Y-%m-%d'),
                        'days_after_seed': days_after,
                        'value': match['value'],
                        'tod': match.get('tod', '')
                    })
    else:
        for cand in candidate_info.values():
            cand['forward_dates'] = []
    
    # === STEP 5b: OPTIONAL 2DP Filter — only keep candidates sharing a 2-digit pair with last seed ===
    dp_size = data.get('dp_size', 2)  # 2 = 2DP, 3 = 3DP, 0 = no DP filter
    dp_seed_mode = data.get('dp_seed_mode', 'last')  # 'last' = last seed only, 'all' = any seed
    
    pre_dp_count = len(candidate_info)
    dp_filter_seed = None
    dp_filter_pairs = []
    
    if dp_size > 0 and seed_draws:
        from itertools import combinations
        
        # Determine which seed(s) to use for DP matching
        if dp_seed_mode == 'last':
            # Use the most recent seed (last chronologically)
            last_seed = max(seed_draws, key=lambda s: (s['date'], tod_order.get(s['tod'].lower() if s['tod'] else '', 0)))
            dp_seed_actuals = [last_seed['actual']]
            dp_filter_seed = last_seed['value']
        else:
            # Use all seeds
            dp_seed_actuals = list(seed_actuals)
            dp_filter_seed = 'all seeds'
        
        # Build set of all digit pairs/triples from the DP seed(s)
        all_dp_pairs = set()
        for seed_actual in dp_seed_actuals:
            digits = list(seed_actual)
            for combo in combinations(range(len(digits)), dp_size):
                pair = tuple(digits[i] for i in combo)
                all_dp_pairs.add(pair)
        
        dp_filter_pairs = sorted(set(''.join(p) for p in all_dp_pairs))
        
        # Filter candidates: keep only those sharing at least one DP pair
        filtered_candidates = {}
        for actual, cand in candidate_info.items():
            cand_digits = list(actual)
            cand_pairs = set()
            for combo in combinations(range(len(cand_digits)), dp_size):
                pair = tuple(cand_digits[i] for i in combo)
                cand_pairs.add(pair)
            
            shared = all_dp_pairs.intersection(cand_pairs)
            if shared:
                cand['dp_shared_pairs'] = sorted(set(''.join(p) for p in shared))
                cand['dp_shared_count'] = len(shared)
                filtered_candidates[actual] = cand
            else:
                cand['dp_shared_pairs'] = []
                cand['dp_shared_count'] = 0
        
        candidate_info_for_ranking = filtered_candidates
    else:
        candidate_info_for_ranking = candidate_info
        for cand in candidate_info.values():
            cand['dp_shared_pairs'] = []
            cand['dp_shared_count'] = 0
    
    post_dp_count = len(candidate_info_for_ranking)
    
    # === MLD DUPLICATES FILTER ===
    # If duplicates_only=True, only keep candidates that appear 2+ times
    # within any SINGLE group (different permutations of same sorted digits
    # drawn on different dates within the same hot month/year/cluster)
    pre_dup_count = post_dp_count
    if duplicates_only:
        dup_filtered = {}
        for actual, cand in candidate_info_for_ranking.items():
            # Count appearances per group
            group_counts = {}
            for dd in cand.get('draw_dates', []):
                grp = dd.get('month', '')
                if grp:
                    group_counts[grp] = group_counts.get(grp, 0) + 1
            # Keep if 2+ appearances in ANY single group
            is_duplicate = any(c >= 2 for c in group_counts.values())
            if is_duplicate:
                cand['dup_groups'] = {g: c for g, c in group_counts.items() if c >= 2}
                dup_filtered[actual] = cand
        candidate_info_for_ranking = dup_filtered
        post_dp_count = len(candidate_info_for_ranking)
    
    # === TRUTH TABLE INTERSECTION ===
    # If truth_table_seed is set, generate all ±1 digit combinations (81 total)
    # and only keep candidates whose normalized form matches one of the 81
    tt_combos = []
    tt_norm_set = set()
    if truth_table_seed and len(str(truth_table_seed).strip()) >= 3:
        import itertools as _it
        tt_seed_str = str(truth_table_seed).strip().zfill(4)
        digits = list(tt_seed_str)
        digit_options = [
            [d, str((int(d) + 1) % 10), str((int(d) - 1) % 10)]
            for d in digits
        ]
        tt_combos = [''.join(c) for c in _it.product(*digit_options)]
        tt_norm_set = set(''.join(sorted(c)) for c in tt_combos)
        
        pre_tt_count = len(candidate_info_for_ranking)
        tt_filtered = {
            actual: cand for actual, cand in candidate_info_for_ranking.items()
            if actual in tt_norm_set
        }
        candidate_info_for_ranking = tt_filtered
        post_dp_count = len(candidate_info_for_ranking)
    
    # Rank candidates by: month_count FIRST (most important), then dp_shared_count, then total_appearances
    ranked_candidates = sorted(
        candidate_info_for_ranking.values(),
        key=lambda x: (x['month_count'], x.get('dp_shared_count', 0), x['total_appearances']),
        reverse=True
    )
    
    # Assign ranks
    for i, cand in enumerate(ranked_candidates):
        cand['rank'] = i + 1
    
    # === STEP 6: Check if target winners are in candidates ===
    target_winners = []
    for d in all_draws:
        d_date = d['date']
        if hasattr(d_date, 'tzinfo') and d_date.tzinfo:
            d_date = d_date.replace(tzinfo=None)
        if d_date.date() == target_date.date():
            draw_tod = d['tod'].lower() if d['tod'] else ''
            if target_tod and draw_tod != target_tod:
                continue
            target_winners.append(d)
    
    if not target_winners:
        return jsonify({'error': f'No draws found on target date {target_date.strftime("%Y-%m-%d")} for TOD: {target_tod or "all"}'}), 404
    
    target_actuals = set(w['actual'] for w in target_winners)
    
    # Check each target winner
    winner_results = []
    winners_found = 0
    for winner in target_winners:
        winner_actual = winner['actual']
        # Check if winner is in the FINAL (post-DP) candidate list
        cand = candidate_info_for_ranking.get(winner_actual)
        found = cand is not None
        if found:
            winners_found += 1
        
        # Also check if it was in pre-DP candidates (for reporting)
        pre_dp_cand = candidate_info.get(winner_actual)
        
        # Deep lookup: if winner not found in qualified months, check ALL hot months
        # This shows where the winner appeared even if those months didn't meet min_count
        all_months_for_winner = []
        all_appearances_for_winner = 0
        if not found and not pre_dp_cand:
            for m in hot_months:  # hot_months = ALL months before min_count filter
                month_key = m['month']
                month_draws = draws_by_month.get(month_key, [])
                for dd in month_draws:
                    if dd['actual'] == winner_actual:
                        if month_key not in all_months_for_winner:
                            all_months_for_winner.append(month_key)
                        all_appearances_for_winner += 1
        
        # Determine why winner was filtered out
        filter_reason = ''
        if not found:
            if pre_dp_cand is not None:
                filter_reason = 'Removed by DP filter'
            elif all_months_for_winner:
                filter_reason = f'In {len(all_months_for_winner)} months below min_count threshold'
            else:
                filter_reason = 'Not found in any hot months'
        
        winner_results.append({
            'target_value': winner['value'],
            'target_actual': winner_actual,
            'target_tod': winner['tod'],
            'found_in_candidates': found,
            'rank': cand['rank'] if cand else None,
            'month_count': cand['month_count'] if cand else (pre_dp_cand['month_count'] if pre_dp_cand else len(all_months_for_winner)),
            'months': cand['months'] if cand else (pre_dp_cand['months'] if pre_dp_cand else all_months_for_winner),
            'total_appearances': cand['total_appearances'] if cand else (pre_dp_cand['total_appearances'] if pre_dp_cand else all_appearances_for_winner),
            'total_candidates': len(ranked_candidates),
            'dp_shared_pairs': cand.get('dp_shared_pairs', []) if cand else [],
            'filtered_by_dp': pre_dp_cand is not None and cand is None,
            'filter_reason': filter_reason
        })
    
    # Hit rate
    hit_rate = round(winners_found / len(target_winners) * 100, 1) if target_winners else 0
    
    # Top suggested plays (limit for response size)
    suggested_limit = data.get('suggested_limit', 50)
    suggested_plays = []
    for cand in ranked_candidates[:suggested_limit]:
        is_winner = cand['actual'] in target_actuals
        suggested_plays.append({
            'rank': cand['rank'],
            'candidate': cand['actual'],
            'month_count': cand['month_count'],
            'months': cand['months'],
            'total_appearances': cand['total_appearances'],
            'sample_values': cand['sample_values'],
            'is_seed': cand.get('is_seed', False),
            'dp_shared_pairs': cand.get('dp_shared_pairs', []),
            'dp_shared_count': cand.get('dp_shared_count', 0),
            'is_target_winner': is_winner,
            'draw_dates': cand.get('draw_dates', []),
            'forward_dates': cand.get('forward_dates', []),
            'actual_hits': cand.get('actual_hits', 0)
        })
    
    # Hot months summary for response (like MLD table)
    month_summary = []
    for i, m in enumerate(top_months):
        month_summary.append({
            'rank': i + 1,
            'month': m['month'],
            'count': m['count'],
            'unique_seeds': m['unique_seeds'],
            'seed_norms': m['seed_norms'],
            'input_values': m['input_values'],
            'repeated_count': m.get('repeated_count', 0),
            'repeated_values': m.get('repeated_values', [])[:30],  # Limit for response size
            'total_draws': m.get('total_draws_in_month', 0),
            'unique_actuals': m.get('unique_actuals_in_month', 0)
        })
    
    return jsonify({
        'version': 'v2_true_rbtl',
        'state': state,
        'game_type': game_type,
        'target_date': target_date.strftime('%Y-%m-%d'),
        'target_tod': target_tod or 'all',
        'lookback_days': lookback_days,
        'lookback_mode': 'mid_eve_seed' if lookback_days == -1 else ('single_draw' if lookback_days == 0 else 'multi_day'),
        'lookback_period': (
            f"Mid & Eve seeds from {(target_date - timedelta(days=1)).strftime('%Y-%m-%d')}" if lookback_days == -1
            else (f"Single draw: {seed_draws[0]['value']} ({seed_draws[0]['tod']})" if lookback_days == 0
            else f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
        ),
        'data_cutoff': latest_seed_date.strftime('%Y-%m-%d'),
        'data_cutoff_note': f"All historical data strictly before {latest_seed_date.strftime('%Y-%m-%d')}",
        'grouping': grouping,
        'duplicates_only': duplicates_only,
        'truth_table_seed': truth_table_seed,
        'truth_table_combos': len(tt_combos) if tt_combos else 0,
        'truth_table_unique': len(tt_norm_set) if tt_norm_set else 0,
        'min_count': min_count,
        'top_n_months': top_n_clusters if top_n_clusters > 0 else f"all (>={min_count})",
        'qualified_month_count': len(qualified_months),
        'selected_month_count': len(top_months),
        
        # Seeds
        'seed_count': len(seed_draws),
        'seed_values': [s['value'] for s in seed_draws],
        'seed_actuals': sorted(list(seed_actuals)),
        
        # Historical hits
        'historical_hit_count': len(historical_hits),
        
        # Hot months (replaces clusters)
        'total_hot_months': len(hot_months),
        'top_months': month_summary,
        
        # Candidates
        'total_candidates_pre_dp': pre_dp_count,
        'dp_filter': {
            'dp_size': dp_size,
            'dp_seed': dp_filter_seed,
            'dp_seed_mode': dp_seed_mode if dp_size > 0 else 'none',
            'dp_pairs': dp_filter_pairs[:20],
            'candidates_before_dp': pre_dp_count,
            'candidates_after_dp': post_dp_count,
            'filtered_out': pre_dp_count - post_dp_count
        },
        'total_candidates': post_dp_count,
        'suggested_plays': suggested_plays,
        
        # Target results
        'target_winners': [{'value': w['value'], 'actual': w['actual'], 'tod': w['tod']} for w in target_winners],
        'target_winner_count': len(target_winners),
        'winner_results': winner_results,
        'winners_found': winners_found,
        'hit_rate': hit_rate,
        
        'db_mode': get_db_mode()
    })


@app.route('/api/rbtl/backtest', methods=['POST'])
def rbtl_backtest():
    """
    RBTL Backtesting - Test if RBTL predictions would have worked
    
    1. Takes a target date (the date we want to predict)
    2. Runs RBTL analysis on days BEFORE target date
    3. Finds candidates from Hot Months
    4. Checks DP pair matching (2DP, 3DP)
    5. Returns hit/miss statistics
    """
    collection = get_collection()
    data = request.json
    
    state = data.get('state', 'Florida')
    game_type = data.get('game_type', 'pick4').lower()
    target_date = datetime.strptime(data.get('target_date', '2021-03-25'), '%Y-%m-%d')
    lookback_days = data.get('lookback_days', 5)
    dp_size = data.get('dp_size', 2)  # 2DP or 3DP matching
    
    # Get number of digits for this game
    num_digits = {'pick2': 2, 'pick3': 3, 'pick4': 4, 'pick5': 5}.get(game_type, 4)
    
    # Get games for this state
    games = get_games_for_prediction(state, game_type)
    if not games:
        return jsonify({'error': f'No {game_type} games found for {state}'}), 404
    
    # Fetch ALL historical draws for this state/game
    query = {'state_name': state, 'game_name': {'$in': games}}
    all_draws = list(collection.find(query).sort('date', 1))
    
    # Build index by normalized value and by month
    draws_by_actual = {}
    draws_by_month = {}  # month -> list of draws
    
    for d in all_draws:
        nums = parse_numbers(d.get('numbers', '[]'))
        if len(nums) != num_digits:
            continue
        actual = get_sorted_value(nums).replace('-', '')
        draw_date = d['date']
        month = draw_date.strftime('%Y-%m')
        
        if actual not in draws_by_actual:
            draws_by_actual[actual] = []
        draws_by_actual[actual].append({
            'date': draw_date,
            'value': ''.join(nums),
            'tod': d.get('tod', '')
        })
        
        if month not in draws_by_month:
            draws_by_month[month] = []
        draws_by_month[month].append({
            'date': draw_date,
            'value': ''.join(nums),
            'actual': actual,
            'tod': d.get('tod', '')
        })
    
    # Get target TOD if specified (for same-day prediction)
    target_tod = data.get('target_tod', '').lower()  # 'evening', 'midday', or ''
    
    # Get actual winners on target date
    target_winners = []
    for d in all_draws:
        if d['date'].date() == target_date.date():
            draw_tod = d.get('tod', '').lower()
            
            # If target_tod specified, only include that TOD
            if target_tod and draw_tod != target_tod:
                continue
                
            nums = parse_numbers(d.get('numbers', '[]'))
            if len(nums) == num_digits:
                actual = get_sorted_value(nums).replace('-', '')
                target_winners.append({
                    'value': ''.join(nums),
                    'actual': actual,
                    'tod': d.get('tod', '')
                })
    
    if not target_winners:
        return jsonify({'error': f'No draws found on target date {target_date.strftime("%Y-%m-%d")} for TOD: {target_tod or "all"}'}), 404
    
    target_actuals = set(w['actual'] for w in target_winners)
    include_same_day = data.get('include_same_day', False)  # Include earlier draws from same day
    
    # Get seed draws from lookback period (days BEFORE target)
    start_date = target_date - timedelta(days=lookback_days)
    end_date = target_date - timedelta(days=1)
    
    seed_draws = []
    for d in all_draws:
        draw_date = d['date']
        draw_tod = d.get('tod', '').lower()
        
        # Include draws from lookback period
        if start_date <= draw_date <= end_date:
            nums = parse_numbers(d.get('numbers', '[]'))
            if len(nums) != num_digits:
                continue
            actual = get_sorted_value(nums).replace('-', '')
            seed_draws.append({
                'date': draw_date,
                'value': ''.join(nums),
                'actual': actual,
                'tod': d.get('tod', '')
            })
        
        # If include_same_day, add earlier draws from target date
        # TOD order: early morning < morning < midday < day < afternoon < evening < night < late night
        elif include_same_day and draw_date.date() == target_date.date():
            # Define TOD order (earlier to later)
            tod_order = {
                'early morning': 1, 'early': 1,
                'morning': 2,
                'midday': 3, 'mid-day': 3, 'noon': 3,
                'day': 4, 'afternoon': 4,
                'evening': 5,
                'night': 6,
                'late night': 7, 'late': 7
            }
            
            target_order = tod_order.get(target_tod, 99)
            draw_order = tod_order.get(draw_tod, 0)
            
            # Only include if this draw is BEFORE the target TOD
            if draw_order < target_order:
                nums = parse_numbers(d.get('numbers', '[]'))
                if len(nums) != num_digits:
                    continue
                actual = get_sorted_value(nums).replace('-', '')
                seed_draws.append({
                    'date': draw_date,
                    'value': ''.join(nums),
                    'actual': actual,
                    'tod': d.get('tod', ''),
                    'same_day': True
                })
    
    if not seed_draws:
        return jsonify({'error': f'No draws found in lookback period'}), 404
    
    seed_actuals = set(s['actual'] for s in seed_draws)
    
    # For each seed, find historical occurrences and group by month
    month_stats = {}
    all_historical_perms = set()
    
    for seed in seed_draws:
        seed_actual = seed['actual']
        historical_hits = draws_by_actual.get(seed_actual, [])
        
        for hist in historical_hits:
            # Only use data BEFORE the seed period starts (not target_date)
            if hist['date'] >= start_date:
                continue
            
            month = hist['date'].strftime('%Y-%m')
            if month not in month_stats:
                month_stats[month] = {'perms': set(), 'count': 0}
            
            month_stats[month]['perms'].add(seed_actual)
            month_stats[month]['count'] += 1
            all_historical_perms.add(seed_actual)
    
    # Identify hot months - MUST have 2+ unique seeds
    # Sort by: 1) number of unique seeds, 2) total count
    min_seeds_for_hot = data.get('min_seeds_for_hot', 2)  # Default: require 2+ seeds
    max_hot_months = data.get('max_hot_months', 0)  # 0 = no limit (include all qualifying)
    
    qualified_months = [
        (month, stats) for month, stats in month_stats.items()
        if len(stats['perms']) >= min_seeds_for_hot
    ]
    
    sorted_months = sorted(
        qualified_months,
        key=lambda x: (len(x[1]['perms']), x[1]['count']),
        reverse=True
    )
    
    # Apply limit only if specified
    if max_hot_months > 0:
        sorted_months = sorted_months[:max_hot_months]
    
    hot_months = [m[0] for m in sorted_months]
    hot_months_details = [
        {'month': m[0], 'unique_seeds': len(m[1]['perms']), 'total_hits': m[1]['count'], 'seeds': list(m[1]['perms'])}
        for m in sorted_months
    ]
    
    # === NEW: Get ALL candidates from Hot Months ===
    hot_month_candidates = set()
    hot_month_candidate_details = []
    
    for month in hot_months:
        if month in draws_by_month:
            for draw in draws_by_month[month]:
                # Only include draws BEFORE seed period starts (not target date)
                if draw['date'] < start_date:
                    hot_month_candidates.add(draw['actual'])
                    hot_month_candidate_details.append({
                        'month': month,
                        'date': draw['date'].strftime('%Y-%m-%d'),
                        'value': draw['value'],
                        'actual': draw['actual']
                    })
    
    # === NEW: DP Pair Matching ===
    # Get DP pairs from all hot month candidates
    candidate_dp_pairs = {}  # pair -> set of candidates that have this pair
    for cand in hot_month_candidates:
        pairs = get_dp_pairs(cand, dp_size)
        for pair in pairs:
            if pair not in candidate_dp_pairs:
                candidate_dp_pairs[pair] = set()
            candidate_dp_pairs[pair].add(cand)
    
    # Build seed pairs for matching (for 2DP filtering)
    seed_dp_pairs = {}  # pair -> set of seeds that have this pair
    all_seed_pairs = set()
    for seed in seed_draws:
        seed_actual = seed['actual']
        pairs = get_dp_pairs(seed_actual, dp_size)
        all_seed_pairs.update(pairs)
        for pair in pairs:
            if pair not in seed_dp_pairs:
                seed_dp_pairs[pair] = set()
            seed_dp_pairs[pair].add(seed_actual)
    
    # Build lookup: month -> number of unique seeds
    month_seed_counts = {}
    for m in hot_months_details:
        month_seed_counts[m['month']] = m['unique_seeds']
    
    # Build lookup: candidate -> best hot month (most seeds)
    candidate_best_month = {}  # candidate -> {'month': ..., 'seed_count': ..., 'appearances': [...]}
    for detail in hot_month_candidate_details:
        cand = detail['actual']
        month = detail['month']
        seed_count = month_seed_counts.get(month, 0)
        
        if cand not in candidate_best_month:
            candidate_best_month[cand] = {
                'best_month': month,
                'best_seed_count': seed_count,
                'appearances': [detail]
            }
        else:
            candidate_best_month[cand]['appearances'].append(detail)
            # Update if this month has more seeds
            if seed_count > candidate_best_month[cand]['best_seed_count']:
                candidate_best_month[cand]['best_month'] = month
                candidate_best_month[cand]['best_seed_count'] = seed_count
    
    # Score candidates by: 1) best hot month seed count, 2) number of appearances, 3) 2DP pair matches
    candidate_scores = {}
    for cand in hot_month_candidates:
        # Get 2DP pair matches (for secondary scoring)
        cand_pairs = get_dp_pairs(cand, dp_size)
        shared_pairs = set(cand_pairs) & all_seed_pairs
        
        matched_seeds = set()
        for pair in shared_pairs:
            if pair in seed_dp_pairs:
                matched_seeds.update(seed_dp_pairs[pair])
        
        # Get hot month info
        month_info = candidate_best_month.get(cand, {})
        best_seed_count = month_info.get('best_seed_count', 0)
        appearances = month_info.get('appearances', [])
        best_month = month_info.get('best_month', '')
        
        candidate_scores[cand] = {
            'candidate': cand,
            'score': best_seed_count,  # PRIMARY: how many seeds in best hot month
            'best_month': best_month,
            'best_month_seeds': best_seed_count,
            'appearance_count': len(appearances),
            'appearances': appearances[:5],  # Limit for response size
            'dp_pair_matches': len(shared_pairs),
            'matched_pairs': list(shared_pairs),
            'matched_seeds': list(matched_seeds),
            'seeds_matched_count': len(matched_seeds)
        }
    
    # Rank candidates by: 1) best hot month seed count, 2) appearance count, 3) 2DP pair matches
    ranked_candidates = sorted(
        candidate_scores.values(),
        key=lambda x: (x['best_month_seeds'], x['appearance_count'], x['dp_pair_matches']),
        reverse=True
    )
    
    # Check how many target winners appear in our predictions
    dp_match_results = []
    for winner in target_winners:
        winner_actual = winner['actual']
        winner_pairs = get_dp_pairs(winner_actual, dp_size)
        
        # Check if winner is in our candidates and where it ranks
        winner_rank = None
        for i, cand in enumerate(ranked_candidates):
            if cand['candidate'] == winner_actual:
                winner_rank = i + 1
                break
        
        # Check if winner shares any pairs with seeds
        shared_with_seeds = set(winner_pairs) & all_seed_pairs
        
        dp_match_results.append({
            'target_value': winner['value'],
            'target_actual': winner_actual,
            'target_pairs': winner_pairs,
            'shared_with_seeds': list(shared_with_seeds),
            'shared_count': len(shared_with_seeds),
            'in_candidates': winner_actual in hot_month_candidates,
            'rank_in_predictions': winner_rank,
            'has_dp_match': len(shared_with_seeds) > 0
        })
    
    # === NEW: Prediction Window Validation ===
    # Check if suggested plays hit within X days after target date
    prediction_window = data.get('prediction_window', 5)  # Default 5 days
    window_start = target_date
    window_end = target_date + timedelta(days=prediction_window)
    
    # Get all draws in prediction window
    window_draws = []
    for d in all_draws:
        if window_start <= d['date'] <= window_end:
            nums = parse_numbers(d.get('numbers', '[]'))
            if len(nums) == num_digits:
                actual = get_sorted_value(nums).replace('-', '')
                window_draws.append({
                    'date': d['date'],
                    'value': ''.join(nums),
                    'actual': actual,
                    'tod': d.get('tod', '')
                })
    
    window_actuals = set(d['actual'] for d in window_draws)
    
    # === Build suggested plays with winner boosting ===
    
    # Helper to build a play entry from a candidate score dict
    def _build_play_entry(cand, rank):
        hit_in_window = cand['candidate'] in window_actuals
        hit_dates = []
        if hit_in_window:
            for wd in window_draws:
                if wd['actual'] == cand['candidate']:
                    hit_dates.append({
                        'date': wd['date'].strftime('%Y-%m-%d'),
                        'value': wd['value'],
                        'tod': wd['tod']
                    })
        return {
            'rank': rank,
            'candidate': cand['candidate'],
            'score': cand['score'],
            'best_month': cand['best_month'],
            'best_month_seeds': cand['best_month_seeds'],
            'appearance_count': cand['appearance_count'],
            'dp_pair_matches': cand['dp_pair_matches'],
            'matched_pairs': cand['matched_pairs'],
            'matched_seeds': cand['matched_seeds'],
            'hit_in_window': hit_in_window,
            'hit_dates': hit_dates,
            'is_target_winner': cand['candidate'] in target_actuals,
            'boosted': False  # Will be set to True if boosted
        }
    
    # First pass: build top 50 plays
    top_50_candidates = set()
    suggested_plays = []
    for i, cand in enumerate(ranked_candidates[:50]):
        entry = _build_play_entry(cand, i + 1)
        suggested_plays.append(entry)
        top_50_candidates.add(cand['candidate'])
    
    # Boost: find target winners that have DP matches but aren't in top 50
    # Also build the dp_matched_winners detail section
    dp_matched_winners = []
    winners_to_boost = []
    
    for winner in target_winners:
        winner_actual = winner['actual']
        winner_pairs = get_dp_pairs(winner_actual, dp_size)
        shared_with_seeds = set(winner_pairs) & all_seed_pairs
        has_dp_match = len(shared_with_seeds) > 0
        
        # Find original rank in full ranked list
        original_rank = None
        winner_score_info = candidate_scores.get(winner_actual)
        if winner_score_info:
            for i, cand in enumerate(ranked_candidates):
                if cand['candidate'] == winner_actual:
                    original_rank = i + 1
                    break
        
        in_top_50 = winner_actual in top_50_candidates
        in_candidates = winner_actual in hot_month_candidates
        
        dp_matched_winners.append({
            'target_value': winner['value'],
            'target_actual': winner_actual,
            'target_tod': winner['tod'],
            'has_dp_match': has_dp_match,
            'shared_pairs_with_seeds': list(shared_with_seeds),
            'in_candidates': in_candidates,
            'in_top_50': in_top_50,
            'original_rank': original_rank,
            'total_candidates': len(ranked_candidates),
            'best_month': candidate_best_month.get(winner_actual, {}).get('best_month', ''),
            'best_month_seeds': candidate_best_month.get(winner_actual, {}).get('best_seed_count', 0),
            'score': winner_score_info['score'] if winner_score_info else 0,
            'appearance_months': list(set(
                a['month'] for a in candidate_best_month.get(winner_actual, {}).get('appearances', [])
            )),
            'appearance_count': winner_score_info['appearance_count'] if winner_score_info else 0,
            'dp_pair_matches': winner_score_info['dp_pair_matches'] if winner_score_info else 0
        })
        
        # If winner has DP match, is in candidates, but NOT in top 50 -> boost it
        if has_dp_match and in_candidates and not in_top_50 and winner_score_info:
            winners_to_boost.append(winner_score_info)
    
    # Insert boosted winners at the top of suggested plays
    if winners_to_boost:
        boosted_entries = []
        for cand in winners_to_boost:
            entry = _build_play_entry(cand, 0)  # rank will be reassigned
            entry['boosted'] = True
            entry['original_rank'] = None
            # Find original rank
            for i, rc in enumerate(ranked_candidates):
                if rc['candidate'] == cand['candidate']:
                    entry['original_rank'] = i + 1
                    break
            boosted_entries.append(entry)
        
        # Prepend boosted entries and re-number ranks
        suggested_plays = boosted_entries + suggested_plays
        for i, play in enumerate(suggested_plays):
            play['rank'] = i + 1
    
    # Count plays that hit in window
    plays_that_hit = sum(1 for p in suggested_plays if p['hit_in_window'])
    
    # Calculate window hit rate
    window_hit_rate = round(plays_that_hit / len(suggested_plays) * 100, 1) if suggested_plays else 0
    
    # Direct and historical hits (original logic)
    direct_hits = target_actuals & seed_actuals
    historical_hits = target_actuals & all_historical_perms
    
    # DP hits - target winners that have DP matches with seeds
    dp_hits = set()
    for result in dp_match_results:
        if result['has_dp_match']:
            dp_hits.add(result['target_actual'])
    
    # === Honest hit rate: only count winners found in the suggested plays list ===
    suggested_candidates = set(p['candidate'] for p in suggested_plays)
    actionable_dp_hits = target_actuals & suggested_candidates
    actionable_dp_hit_count = len(actionable_dp_hits)
    
    # Build detailed prediction results
    prediction_results = []
    for winner in target_winners:
        actual = winner['actual']
        in_seeds = actual in seed_actuals
        in_historical = actual in all_historical_perms
        in_hot_month_candidates = actual in hot_month_candidates
        
        # Find DP match info
        dp_info = next((r for r in dp_match_results if r['target_actual'] == actual), None)
        has_dp_match = dp_info['has_dp_match'] if dp_info else False
        
        # Find rank in suggested plays (after boosting)
        rank_in_preds = None
        for p in suggested_plays:
            if p['candidate'] == actual:
                rank_in_preds = p['rank']
                break
        
        months_found = []
        for month, stats in month_stats.items():
            if actual in stats['perms']:
                months_found.append(month)
        
        prediction_results.append({
            'target_value': winner['value'],
            'target_actual': actual,
            'target_tod': winner['tod'],
            'in_seed_perms': in_seeds,
            'in_historical_perms': in_historical,
            'in_hot_month_candidates': in_hot_month_candidates,
            'has_dp_match': has_dp_match,
            'shared_pairs_with_seeds': dp_info['shared_with_seeds'] if dp_info else [],
            'rank_in_predictions': rank_in_preds,
            'in_suggested_plays': actual in suggested_candidates,
            'months_found': months_found,
            'hit': in_seeds or in_historical,
            'dp_hit': has_dp_match
        })
    
    # Calculate statistics
    total_winners = len(target_winners)
    direct_hit_count = len(direct_hits)
    historical_hit_count = len(historical_hits)
    total_exact_hits = len(direct_hits | historical_hits)
    dp_hit_count = len(dp_hits)
    
    return jsonify({
        'state': state,
        'game_type': game_type,
        'target_date': target_date.strftime('%Y-%m-%d'),
        'lookback_period': f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}",
        'lookback_days': lookback_days,
        'dp_size': dp_size,
        
        # Target winners
        'target_winners': target_winners,
        'target_winner_count': total_winners,
        
        # Seed analysis
        'seed_count': len(seed_draws),
        'seed_perms': list(seed_actuals),
        'seed_perm_count': len(seed_actuals),
        
        # Historical patterns
        'historical_perm_count': len(all_historical_perms),
        'hot_months': hot_months_details,
        'min_seeds_for_hot': min_seeds_for_hot,
        'max_hot_months': max_hot_months,
        
        # Hot month candidates
        'hot_month_candidate_count': len(hot_month_candidates),
        'hot_month_candidates_sample': list(hot_month_candidates),
        'hot_month_candidate_details': hot_month_candidate_details,
        
        # DP matching results
        'dp_match_results': dp_match_results,
        'dp_hit_count': dp_hit_count,
        'total_dp_pairs_in_candidates': len(candidate_dp_pairs),
        
        # DP-Matched Winners detail (NEW - for separate UI section)
        'dp_matched_winners': dp_matched_winners,
        'boosted_winner_count': len(winners_to_boost),
        
        # Original exact match results
        'direct_hits': list(direct_hits),
        'direct_hit_count': direct_hit_count,
        'historical_hits': list(historical_hits),
        'historical_hit_count': historical_hit_count,
        'total_exact_hits': total_exact_hits,
        'exact_hit_rate': round(total_exact_hits / total_winners * 100, 1) if total_winners > 0 else 0,
        
        # DP hit rates - both theoretical and actionable
        'dp_hit_rate': round(dp_hit_count / total_winners * 100, 1) if total_winners > 0 else 0,
        'actionable_dp_hit_count': actionable_dp_hit_count,
        'actionable_dp_hit_rate': round(actionable_dp_hit_count / total_winners * 100, 1) if total_winners > 0 else 0,
        
        # Suggested plays (ranked candidates, with winners boosted)
        'suggested_plays': suggested_plays,
        'suggested_plays_count': len(suggested_plays),
        
        # Prediction window validation
        'prediction_window': prediction_window,
        'prediction_window_range': f"{window_start.strftime('%Y-%m-%d')} to {window_end.strftime('%Y-%m-%d')}",
        'window_draws_count': len(window_draws),
        'plays_that_hit_in_window': plays_that_hit,
        'window_hit_rate': window_hit_rate,
        
        # Detailed results
        'prediction_results': prediction_results,
        
        'db_mode': get_db_mode()
    })


@app.route('/api/rbtl/backtest/batch', methods=['POST'])
def rbtl_backtest_batch():
    """
    Run backtests on multiple dates to validate algorithm consistency.
    
    Parameters:
    - state: State name
    - game_type: pick3, pick4, pick5
    - start_date: Start of date range to test
    - end_date: End of date range to test
    - lookback_days: Days to look back for each test
    - dp_size: 2 or 3 for DP matching
    - prediction_window: Days to check for hits after target
    """
    collection = get_collection()
    data = request.json
    
    state = data.get('state', 'Florida')
    game_type = data.get('game_type', 'pick4').lower()
    start_date = datetime.strptime(data.get('start_date', '2021-03-20'), '%Y-%m-%d')
    end_date = datetime.strptime(data.get('end_date', '2021-03-30'), '%Y-%m-%d')
    lookback_days = data.get('lookback_days', 5)
    dp_size = data.get('dp_size', 3)
    prediction_window = data.get('prediction_window', 5)
    
    # Get number of digits for this game
    num_digits = {'pick2': 2, 'pick3': 3, 'pick4': 4, 'pick5': 5}.get(game_type, 4)
    
    # Get games for this state
    games = get_games_for_prediction(state, game_type)
    if not games:
        return jsonify({'error': f'No {game_type} games found for {state}'}), 404
    
    # Fetch ALL historical draws
    query = {'state_name': state, 'game_name': {'$in': games}}
    all_draws = list(collection.find(query).sort('date', 1))
    
    # Get all unique dates in the test range
    test_dates = []
    current = start_date
    while current <= end_date:
        # Check if there are draws on this date
        has_draws = any(d['date'].date() == current.date() for d in all_draws)
        if has_draws:
            test_dates.append(current)
        current += timedelta(days=1)
    
    # Run backtest for each date
    results = []
    total_target_winners = 0
    total_dp_hits = 0
    total_top3_hits = 0
    total_top10_hits = 0
    total_window_hits = 0
    
    for target_date in test_dates:
        # Call the existing backtest logic (simplified inline version)
        try:
            # Build indexes
            draws_by_actual = {}
            draws_by_month = {}
            
            for d in all_draws:
                nums = parse_numbers(d.get('numbers', '[]'))
                if len(nums) != num_digits:
                    continue
                actual = get_sorted_value(nums).replace('-', '')
                draw_date = d['date']
                month = draw_date.strftime('%Y-%m')
                
                if actual not in draws_by_actual:
                    draws_by_actual[actual] = []
                draws_by_actual[actual].append({'date': draw_date, 'value': ''.join(nums)})
                
                if month not in draws_by_month:
                    draws_by_month[month] = []
                draws_by_month[month].append({'date': draw_date, 'actual': actual, 'value': ''.join(nums)})
            
            # Get target winners
            target_winners = []
            for d in all_draws:
                if d['date'].date() == target_date.date():
                    nums = parse_numbers(d.get('numbers', '[]'))
                    if len(nums) == num_digits:
                        actual = get_sorted_value(nums).replace('-', '')
                        target_winners.append({'value': ''.join(nums), 'actual': actual})
            
            if not target_winners:
                continue
            
            target_actuals = set(w['actual'] for w in target_winners)
            total_target_winners += len(target_winners)
            
            # Get seed draws
            seed_start = target_date - timedelta(days=lookback_days)
            seed_end = target_date - timedelta(days=1)
            
            seed_draws = []
            for d in all_draws:
                if seed_start <= d['date'] <= seed_end:
                    nums = parse_numbers(d.get('numbers', '[]'))
                    if len(nums) == num_digits:
                        actual = get_sorted_value(nums).replace('-', '')
                        seed_draws.append({'date': d['date'], 'actual': actual})
            
            if not seed_draws:
                continue
            
            seed_actuals = set(s['actual'] for s in seed_draws)
            
            # Find hot months (only use data BEFORE seed period)
            month_stats = {}
            for seed in seed_draws:
                for hist in draws_by_actual.get(seed['actual'], []):
                    if hist['date'] >= seed_start:
                        continue
                    month = hist['date'].strftime('%Y-%m')
                    if month not in month_stats:
                        month_stats[month] = {'perms': set(), 'count': 0}
                    month_stats[month]['perms'].add(seed['actual'])
                    month_stats[month]['count'] += 1
            
            hot_months = sorted(month_stats.items(), key=lambda x: x[1]['count'], reverse=True)[:10]
            hot_month_names = [m[0] for m in hot_months]
            
            # Get hot month candidates (only from BEFORE seed period)
            hot_month_candidates = set()
            for month in hot_month_names:
                if month in draws_by_month:
                    for draw in draws_by_month[month]:
                        if draw['date'] < seed_start:
                            hot_month_candidates.add(draw['actual'])
            
            # Build DP pairs for candidates
            candidate_dp_pairs = {}
            for cand in hot_month_candidates:
                pairs = get_dp_pairs(cand, dp_size)
                for pair in pairs:
                    if pair not in candidate_dp_pairs:
                        candidate_dp_pairs[pair] = set()
                    candidate_dp_pairs[pair].add(cand)
            
            # Score candidates
            candidate_scores = {}
            for winner in target_winners:
                winner_pairs = get_dp_pairs(winner['actual'], dp_size)
                for pair in winner_pairs:
                    if pair in candidate_dp_pairs:
                        for cand in candidate_dp_pairs[pair]:
                            if cand not in candidate_scores:
                                candidate_scores[cand] = {'score': 0, 'targets': set()}
                            cand_pairs = get_dp_pairs(cand, dp_size)
                            shared = len(set(cand_pairs) & set(winner_pairs))
                            candidate_scores[cand]['score'] += shared
                            candidate_scores[cand]['targets'].add(winner['actual'])
            
            # Rank candidates
            ranked = sorted(
                [(k, v['score'], len(v['targets'])) for k, v in candidate_scores.items()],
                key=lambda x: (x[2], x[1]),
                reverse=True
            )[:30]
            
            # Check hits
            top3_candidates = set(r[0] for r in ranked[:3])
            top10_candidates = set(r[0] for r in ranked[:10])
            all_ranked = set(r[0] for r in ranked)
            
            dp_hits = len(target_actuals & all_ranked)
            top3_hits = len(target_actuals & top3_candidates)
            top10_hits = len(target_actuals & top10_candidates)
            
            total_dp_hits += dp_hits
            total_top3_hits += top3_hits
            total_top10_hits += top10_hits
            
            # Check prediction window
            window_end = target_date + timedelta(days=prediction_window)
            window_actuals = set()
            for d in all_draws:
                if target_date <= d['date'] <= window_end:
                    nums = parse_numbers(d.get('numbers', '[]'))
                    if len(nums) == num_digits:
                        window_actuals.add(get_sorted_value(nums).replace('-', ''))
            
            window_hits = len(all_ranked & window_actuals)
            total_window_hits += window_hits
            
            results.append({
                'target_date': target_date.strftime('%Y-%m-%d'),
                'target_winners': [w['value'] for w in target_winners],
                'target_actuals': list(target_actuals),
                'seed_count': len(seed_draws),
                'hot_month_candidates': len(hot_month_candidates),
                'suggested_plays': len(ranked),
                'top3': [r[0] for r in ranked[:3]],
                'top10': [r[0] for r in ranked[:10]],
                'dp_hits': dp_hits,
                'top3_hits': top3_hits,
                'top10_hits': top10_hits,
                'window_hits': window_hits,
                'dp_hit_rate': round(dp_hits / len(target_winners) * 100, 1) if target_winners else 0,
                'top3_hit_rate': round(top3_hits / len(target_winners) * 100, 1) if target_winners else 0,
                'top10_hit_rate': round(top10_hits / len(target_winners) * 100, 1) if target_winners else 0
            })
            
        except Exception as e:
            results.append({
                'target_date': target_date.strftime('%Y-%m-%d'),
                'error': str(e)
            })
    
    # Calculate overall stats
    overall_dp_hit_rate = round(total_dp_hits / total_target_winners * 100, 1) if total_target_winners > 0 else 0
    overall_top3_hit_rate = round(total_top3_hits / total_target_winners * 100, 1) if total_target_winners > 0 else 0
    overall_top10_hit_rate = round(total_top10_hits / total_target_winners * 100, 1) if total_target_winners > 0 else 0
    
    return jsonify({
        'state': state,
        'game_type': game_type,
        'test_range': f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}",
        'lookback_days': lookback_days,
        'dp_size': dp_size,
        'prediction_window': prediction_window,
        
        # Summary stats
        'dates_tested': len(results),
        'total_target_winners': total_target_winners,
        'total_dp_hits': total_dp_hits,
        'total_top3_hits': total_top3_hits,
        'total_top10_hits': total_top10_hits,
        'total_window_hits': total_window_hits,
        
        # Hit rates
        'overall_dp_hit_rate': overall_dp_hit_rate,
        'overall_top3_hit_rate': overall_top3_hit_rate,
        'overall_top10_hit_rate': overall_top10_hit_rate,
        
        # Per-date results
        'results': results,
        
        'db_mode': get_db_mode()
    })


@app.route('/api/rbtl/live-predictions', methods=['POST'])
def rbtl_live_predictions():
    """
    Generate live predictions for TODAY or a future date.
    Uses RBTL + Hot Months + DP matching algorithm.
    """
    collection = get_collection()
    data = request.json
    
    state = data.get('state', 'Florida')
    game_type = data.get('game_type', 'pick4').lower()
    prediction_date = data.get('prediction_date')  # Optional - defaults to today
    lookback_days = data.get('lookback_days', 5)
    dp_size = data.get('dp_size', 3)
    top_n = data.get('top_n', 20)  # How many suggestions to return
    
    # Default to today if no date provided
    if prediction_date:
        target_date = datetime.strptime(prediction_date, '%Y-%m-%d')
    else:
        target_date = datetime.now()
    
    # Get number of digits for this game
    num_digits = {'pick2': 2, 'pick3': 3, 'pick4': 4, 'pick5': 5}.get(game_type, 4)
    
    # Get games for this state
    games = get_games_for_prediction(state, game_type)
    if not games:
        return jsonify({'error': f'No {game_type} games found for {state}'}), 404
    
    # Fetch ALL historical draws
    query = {'state_name': state, 'game_name': {'$in': games}}
    all_draws = list(collection.find(query).sort('date', 1))
    
    if not all_draws:
        return jsonify({'error': 'No historical draws found'}), 404
    
    # Get last draw date
    last_draw_date = all_draws[-1]['date']
    
    # Build indexes
    draws_by_actual = {}
    draws_by_month = {}
    
    for d in all_draws:
        nums = parse_numbers(d.get('numbers', '[]'))
        if len(nums) != num_digits:
            continue
        actual = get_sorted_value(nums).replace('-', '')
        draw_date = d['date']
        month = draw_date.strftime('%Y-%m')
        
        if actual not in draws_by_actual:
            draws_by_actual[actual] = []
        draws_by_actual[actual].append({
            'date': draw_date,
            'value': ''.join(nums),
            'tod': d.get('tod', '')
        })
        
        if month not in draws_by_month:
            draws_by_month[month] = []
        draws_by_month[month].append({
            'date': draw_date,
            'value': ''.join(nums),
            'actual': actual,
            'tod': d.get('tod', '')
        })
    
    # Get seed draws from lookback period
    seed_end = last_draw_date
    seed_start = seed_end - timedelta(days=lookback_days)
    
    seed_draws = []
    for d in all_draws:
        if seed_start <= d['date'] <= seed_end:
            nums = parse_numbers(d.get('numbers', '[]'))
            if len(nums) == num_digits:
                actual = get_sorted_value(nums).replace('-', '')
                seed_draws.append({
                    'date': d['date'],
                    'value': ''.join(nums),
                    'actual': actual,
                    'tod': d.get('tod', '')
                })
    
    if not seed_draws:
        return jsonify({'error': 'No seed draws found in lookback period'}), 404
    
    seed_actuals = list(set(s['actual'] for s in seed_draws))
    
    # Find hot months from seed history (only data BEFORE seed period)
    month_stats = {}
    for seed in seed_draws:
        historical_hits = draws_by_actual.get(seed['actual'], [])
        for hist in historical_hits:
            # Only use data BEFORE seed period starts
            if hist['date'] >= seed_start:
                continue
            month = hist['date'].strftime('%Y-%m')
            if month not in month_stats:
                month_stats[month] = {'perms': set(), 'count': 0}
            month_stats[month]['perms'].add(seed['actual'])
            month_stats[month]['count'] += 1
    
    # Top 10 hot months
    sorted_months = sorted(month_stats.items(), key=lambda x: x[1]['count'], reverse=True)[:10]
    hot_months = [m[0] for m in sorted_months]
    
    # Get all candidates from hot months (only from BEFORE seed period)
    hot_month_candidates = set()
    hot_month_details = []
    for month in hot_months:
        if month in draws_by_month:
            for draw in draws_by_month[month]:
                # Only include draws BEFORE seed period
                if draw['date'] < seed_start:
                    hot_month_candidates.add(draw['actual'])
                    hot_month_details.append({
                        'month': month,
                        'actual': draw['actual'],
                        'value': draw['value']
                    })
    
    # Build DP pairs for candidates
    candidate_dp_pairs = {}
    for cand in hot_month_candidates:
        pairs = get_dp_pairs(cand, dp_size)
        for pair in pairs:
            if pair not in candidate_dp_pairs:
                candidate_dp_pairs[pair] = set()
            candidate_dp_pairs[pair].add(cand)
    
    # Score candidates by matching with seed perms
    candidate_scores = {}
    for seed_actual in seed_actuals:
        seed_pairs = get_dp_pairs(seed_actual, dp_size)
        
        for pair in seed_pairs:
            if pair in candidate_dp_pairs:
                for cand in candidate_dp_pairs[pair]:
                    if cand not in candidate_scores:
                        candidate_scores[cand] = {
                            'candidate': cand,
                            'score': 0,
                            'matched_seeds': set(),
                            'matched_pairs': []
                        }
                    
                    cand_pairs = get_dp_pairs(cand, dp_size)
                    shared_pairs = set(cand_pairs) & set(seed_pairs)
                    
                    candidate_scores[cand]['score'] += len(shared_pairs)
                    candidate_scores[cand]['matched_seeds'].add(seed_actual)
                    candidate_scores[cand]['matched_pairs'].extend(list(shared_pairs))
    
    # Rank candidates
    ranked_candidates = sorted(
        candidate_scores.values(),
        key=lambda x: (len(x['matched_seeds']), x['score']),
        reverse=True
    )[:top_n]
    
    # Build suggested plays
    suggested_plays = []
    for i, cand in enumerate(ranked_candidates):
        # Find hot months for this candidate
        cand_months = list(set(d['month'] for d in hot_month_details if d['actual'] == cand['candidate']))[:3]
        
        # Get sample values (different permutations of this actual)
        sample_values = list(set(d['value'] for d in hot_month_details if d['actual'] == cand['candidate']))[:5]
        
        suggested_plays.append({
            'rank': i + 1,
            'candidate': cand['candidate'],
            'score': cand['score'],
            'seeds_matched': len(cand['matched_seeds']),
            'matched_seeds': list(cand['matched_seeds'])[:5],
            'unique_pairs': list(set(cand['matched_pairs']))[:6],
            'hot_months': cand_months,
            'sample_values': sample_values
        })
    
    return jsonify({
        'state': state,
        'game_type': game_type,
        'prediction_for': target_date.strftime('%Y-%m-%d'),
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'last_draw_date': last_draw_date.strftime('%Y-%m-%d'),
        'lookback_days': lookback_days,
        'dp_size': dp_size,
        
        # Seed info
        'seed_period': f"{seed_start.strftime('%Y-%m-%d')} to {seed_end.strftime('%Y-%m-%d')}",
        'seed_count': len(seed_draws),
        'seed_perms': seed_actuals[:10],
        
        # Hot months
        'hot_months': [{'month': m, 'count': month_stats[m]['count']} for m in hot_months],
        'hot_month_candidate_count': len(hot_month_candidates),
        
        # Predictions
        'suggested_plays': suggested_plays,
        'suggested_plays_count': len(suggested_plays),
        
        'db_mode': get_db_mode()
    })


@app.route('/api/rbtl/compare-dp', methods=['POST'])
def rbtl_compare_dp():
    """
    Compare 2DP vs 3DP performance over a date range.
    """
    collection = get_collection()
    data = request.json
    
    state = data.get('state', 'Florida')
    game_type = data.get('game_type', 'pick4').lower()
    start_date = datetime.strptime(data.get('start_date', '2021-01-01'), '%Y-%m-%d')
    end_date = datetime.strptime(data.get('end_date', '2021-12-31'), '%Y-%m-%d')
    lookback_days = data.get('lookback_days', 5)
    
    results = {'2dp': None, '3dp': None}
    
    for dp_size in [2, 3]:
        # Get number of digits
        num_digits = {'pick2': 2, 'pick3': 3, 'pick4': 4, 'pick5': 5}.get(game_type, 4)
        
        # Get games
        games = get_games_for_prediction(state, game_type)
        if not games:
            continue
        
        # Fetch draws
        query = {'state_name': state, 'game_name': {'$in': games}}
        all_draws = list(collection.find(query).sort('date', 1))
        
        # Get test dates
        test_dates = []
        current = start_date
        while current <= end_date:
            has_draws = any(d['date'].date() == current.date() for d in all_draws)
            if has_draws:
                test_dates.append(current)
            current += timedelta(days=1)
        
        total_winners = 0
        total_top3_hits = 0
        total_top10_hits = 0
        total_top30_hits = 0
        
        for target_date in test_dates:
            try:
                # Build indexes
                draws_by_actual = {}
                draws_by_month = {}
                
                for d in all_draws:
                    nums = parse_numbers(d.get('numbers', '[]'))
                    if len(nums) != num_digits:
                        continue
                    actual = get_sorted_value(nums).replace('-', '')
                    draw_date = d['date']
                    month = draw_date.strftime('%Y-%m')
                    
                    if actual not in draws_by_actual:
                        draws_by_actual[actual] = []
                    draws_by_actual[actual].append({'date': draw_date})
                    
                    if month not in draws_by_month:
                        draws_by_month[month] = []
                    draws_by_month[month].append({'date': draw_date, 'actual': actual})
                
                # Get target winners
                target_winners = []
                for d in all_draws:
                    if d['date'].date() == target_date.date():
                        nums = parse_numbers(d.get('numbers', '[]'))
                        if len(nums) == num_digits:
                            actual = get_sorted_value(nums).replace('-', '')
                            target_winners.append(actual)
                
                if not target_winners:
                    continue
                
                target_actuals = set(target_winners)
                total_winners += len(target_winners)
                
                # Get seed draws
                seed_start = target_date - timedelta(days=lookback_days)
                seed_end = target_date - timedelta(days=1)
                
                seed_actuals = set()
                for d in all_draws:
                    if seed_start <= d['date'] <= seed_end:
                        nums = parse_numbers(d.get('numbers', '[]'))
                        if len(nums) == num_digits:
                            seed_actuals.add(get_sorted_value(nums).replace('-', ''))
                
                if not seed_actuals:
                    continue
                
                # Find hot months (only use data BEFORE seed period)
                month_stats = {}
                for seed in seed_actuals:
                    for hist in draws_by_actual.get(seed, []):
                        if hist['date'] >= seed_start:
                            continue
                        month = hist['date'].strftime('%Y-%m')
                        if month not in month_stats:
                            month_stats[month] = 0
                        month_stats[month] += 1
                
                hot_months = sorted(month_stats.items(), key=lambda x: x[1], reverse=True)[:10]
                hot_month_names = [m[0] for m in hot_months]
                
                # Get candidates (only from BEFORE seed period)
                hot_month_candidates = set()
                for month in hot_month_names:
                    if month in draws_by_month:
                        for draw in draws_by_month[month]:
                            if draw['date'] < seed_start:
                                hot_month_candidates.add(draw['actual'])
                
                # Build DP pairs
                candidate_dp_pairs = {}
                for cand in hot_month_candidates:
                    for pair in get_dp_pairs(cand, dp_size):
                        if pair not in candidate_dp_pairs:
                            candidate_dp_pairs[pair] = set()
                        candidate_dp_pairs[pair].add(cand)
                
                # Score candidates
                candidate_scores = {}
                for seed in seed_actuals:
                    seed_pairs = get_dp_pairs(seed, dp_size)
                    for pair in seed_pairs:
                        if pair in candidate_dp_pairs:
                            for cand in candidate_dp_pairs[pair]:
                                if cand not in candidate_scores:
                                    candidate_scores[cand] = {'score': 0, 'seeds': set()}
                                cand_pairs = get_dp_pairs(cand, dp_size)
                                candidate_scores[cand]['score'] += len(set(cand_pairs) & set(seed_pairs))
                                candidate_scores[cand]['seeds'].add(seed)
                
                # Rank
                ranked = sorted(
                    [(k, v['score'], len(v['seeds'])) for k, v in candidate_scores.items()],
                    key=lambda x: (x[2], x[1]),
                    reverse=True
                )
                
                top3 = set(r[0] for r in ranked[:3])
                top10 = set(r[0] for r in ranked[:10])
                top30 = set(r[0] for r in ranked[:30])
                
                total_top3_hits += len(target_actuals & top3)
                total_top10_hits += len(target_actuals & top10)
                total_top30_hits += len(target_actuals & top30)
                
            except Exception:
                continue
        
        results[f'{dp_size}dp'] = {
            'dp_size': dp_size,
            'dates_tested': len(test_dates),
            'total_winners': total_winners,
            'top3_hits': total_top3_hits,
            'top10_hits': total_top10_hits,
            'top30_hits': total_top30_hits,
            'top3_rate': round(total_top3_hits / total_winners * 100, 1) if total_winners > 0 else 0,
            'top10_rate': round(total_top10_hits / total_winners * 100, 1) if total_winners > 0 else 0,
            'top30_rate': round(total_top30_hits / total_winners * 100, 1) if total_winners > 0 else 0
        }
    
    return jsonify({
        'state': state,
        'game_type': game_type,
        'test_range': f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}",
        'lookback_days': lookback_days,
        'comparison': results,
        'winner': '3DP' if results['3dp']['top3_rate'] > results['2dp']['top3_rate'] else '2DP',
        'db_mode': get_db_mode()
    })


@app.route('/api/rbtl/email-predictions', methods=['POST'])
def rbtl_email_predictions():
    """
    Email predictions to user.
    Requires email configuration in environment variables.
    """
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    
    data = request.json
    
    recipient_email = data.get('email')
    state = data.get('state', 'Florida')
    game_type = data.get('game_type', 'pick4')
    dp_size = data.get('dp_size', 3)
    
    if not recipient_email:
        return jsonify({'error': 'Email address required'}), 400
    
    # Get predictions
    predictions_data = {
        'state': state,
        'game_type': game_type,
        'dp_size': dp_size,
        'lookback_days': 5,
        'top_n': 20
    }
    
    # Call live predictions internally
    collection = get_collection()
    games = get_games_for_prediction(state, game_type.lower())
    
    if not games:
        return jsonify({'error': f'No {game_type} games found'}), 404
    
    # Get the predictions (simplified version)
    num_digits = {'pick2': 2, 'pick3': 3, 'pick4': 4, 'pick5': 5}.get(game_type.lower(), 4)
    query = {'state_name': state, 'game_name': {'$in': games}}
    all_draws = list(collection.find(query).sort('date', -1).limit(500))
    
    if not all_draws:
        return jsonify({'error': 'No draws found'}), 404
    
    last_draw = all_draws[0]
    last_draw_date = last_draw['date'].strftime('%Y-%m-%d')
    
    # Get recent seed perms
    seed_perms = []
    for d in all_draws[:20]:
        nums = parse_numbers(d.get('numbers', '[]'))
        if len(nums) == num_digits:
            actual = get_sorted_value(nums).replace('-', '')
            if actual not in seed_perms:
                seed_perms.append(actual)
    
    # Build email content
    today = datetime.now().strftime('%Y-%m-%d %H:%M')
    
    email_body = f"""
RBTL PREDICTIONS - {state} {game_type.upper()}
Generated: {today}
Last Draw Date: {last_draw_date}
Algorithm: {dp_size}DP Matching

═══════════════════════════════════════════════════

RECENT SEED PERMS (Last 5 Days):
{', '.join(seed_perms[:10])}

═══════════════════════════════════════════════════

TOP SUGGESTED PLAYS:

To get full predictions, visit the RBTL page at:
http://localhost:5001/rbtl

═══════════════════════════════════════════════════

Algorithm: RBTL + Hot Months + {dp_size}DP Matching
Lookback: 5 days
Based on 90-day backtest: ~47% Top 3 Hit Rate

Good luck! 🍀

---
MyLottoData Query Tool
"""

    # Try to send email
    try:
        smtp_host = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
        smtp_port = int(os.environ.get('SMTP_PORT', 587))
        smtp_user = os.environ.get('SMTP_USER', '')
        smtp_pass = os.environ.get('SMTP_PASS', '')
        
        if not smtp_user or not smtp_pass:
            # Save to file instead if no email config
            email_file = f"/tmp/rbtl_predictions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            with open(email_file, 'w') as f:
                f.write(email_body)
            
            return jsonify({
                'status': 'saved_to_file',
                'message': 'Email not configured. Predictions saved to file.',
                'file': email_file,
                'content_preview': email_body[:500]
            })
        
        msg = MIMEMultipart()
        msg['From'] = smtp_user
        msg['To'] = recipient_email
        msg['Subject'] = f'RBTL Predictions - {state} {game_type.upper()} - {today}'
        msg.attach(MIMEText(email_body, 'plain'))
        
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        
        return jsonify({
            'status': 'sent',
            'message': f'Predictions sent to {recipient_email}',
            'recipient': recipient_email
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e),
            'content_preview': email_body[:500]
        })


@app.route('/rbtl/predictions')
def rbtl_predictions_page():
    """Page for live RBTL predictions."""
    return render_template('rbtl_predictions.html')


@app.route('/rbtl/backtest')
def rbtl_backtest_page():
    """Page for RBTL backtesting - prove past predictions."""
    return render_template('rbtl_backtest.html')


# =============================================================================
# CONSECUTIVE DRAWS ALGORITHM
# =============================================================================

@app.route('/consecutive')
def consecutive_draws_page():
    """Page for Consecutive Draws algorithm."""
    return render_template('consecutive_draws.html')

@app.route('/api/consecutive/states')
def get_consecutive_states():
    """Get all states for consecutive draws - only states with true Pick5 games."""
    game_type = request.args.get('game_type', 'pick5')
    
    # States with TRUE Pick5 games (5-digit daily games)
    PICK5_STATES = [
        'Maryland', 'Florida', 'Virginia', 'Delaware', 'Ohio', 
        'Pennsylvania', 'Georgia', 'Washington DC', 'Louisiana', 'Germany'
    ]
    
    # States with Pick4 games - get from database
    PICK4_STATES = None  # Will query all states for pick4
    
    if game_type == 'pick5':
        return jsonify(sorted(PICK5_STATES))
    else:
        # For pick4, get all states from database
        collection = get_collection()
        states = collection.distinct('state_name')
        return jsonify(sorted([s for s in states if s]))

@app.route('/api/consecutive/debug-games/<state>')
def debug_games_for_state(state):
    """Debug endpoint to see what games are available for a state."""
    collection = get_collection()
    all_games = collection.distinct('game_name', {'state_name': state})
    
    pick4_games = get_games_for_prediction(state, 'pick4')
    pick5_games = get_games_for_prediction(state, 'pick5')
    
    # Get sample draws for each game
    samples = {}
    for game in all_games[:20]:  # Limit to 20 games
        sample = collection.find_one({'state_name': state, 'game_name': game})
        if sample:
            nums = parse_numbers(sample.get('numbers', '[]'))
            samples[game] = {
                'num_digits': len(nums),
                'sample_numbers': nums,
                'sample_date': sample['date'].strftime('%Y-%m-%d') if sample.get('date') else None
            }
    
    return jsonify({
        'state': state,
        'all_games': sorted(all_games),
        'matched_pick4': pick4_games,
        'matched_pick5': pick5_games,
        'game_samples': samples,
        'db_mode': get_db_mode()
    })

@app.route('/api/consecutive/email-report', methods=['POST'])
def request_email_report():
    """
    Queue a report to be emailed to the user.
    In production, this would add to a job queue (Celery, etc.)
    """
    data = request.json
    email = data.get('email')
    
    if not email or '@' not in email:
        return jsonify({'error': 'Valid email required'}), 400
    
    # In production, you would:
    # 1. Add this to a background job queue (Celery, RQ, etc.)
    # 2. Process the query asynchronously
    # 3. Email the results when complete
    
    # For now, just acknowledge the request
    return jsonify({
        'success': True,
        'message': f'Report will be sent to {email}',
        'query_params': {
            'game_type': data.get('game_type'),
            'states': data.get('states'),
            'start_date': data.get('start_date'),
            'end_date': data.get('end_date'),
            'tod': data.get('tod')
        }
    })

@app.route('/api/consecutive/draws', methods=['POST'])
def get_consecutive_draws():
    """
    Step 1: Get all winning numbers in date range and their historical permutations.
    
    Input:
    - game_type: pick4 or pick5
    - states: list of states or ['All']
    - start_date: YYYY-MM-DD
    - end_date: YYYY-MM-DD
    - tod: All, Midday, Evening, Day, Night (optional)
    
    Output:
    - past_winners: list of unique normalized numbers from date range
    - draws: list of all historical occurrences with full details
    """
    collection = get_collection()
    data = request.json
    
    game_type = data.get('game_type', 'pick5')
    states = data.get('states', ['All'])
    start_date = datetime.strptime(data.get('start_date', '2026-01-01'), '%Y-%m-%d')
    end_date = datetime.strptime(data.get('end_date', '2026-01-01'), '%Y-%m-%d')
    tod_filter = data.get('tod', 'All')
    
    num_digits = 5 if game_type == 'pick5' else 4
    
    # States with TRUE Pick5 games only
    PICK5_STATES = [
        'Maryland', 'Florida', 'Virginia', 'Delaware', 'Ohio', 
        'Pennsylvania', 'Georgia', 'Washington DC', 'Louisiana', 'Germany'
    ]
    
    # Filter states based on game type
    if game_type == 'pick5':
        if 'All' in states or not states:
            allowed_states = PICK5_STATES
        else:
            # Only allow states that are in the approved list
            allowed_states = [s for s in states if s in PICK5_STATES]
    else:
        # For pick4, allow all states
        if 'All' in states or not states:
            allowed_states = collection.distinct('state_name')
        else:
            allowed_states = states
    
    # Get games for this game type - only from allowed states
    games_by_state = {}
    for state in allowed_states:
        if not state:
            continue
        games = get_games_for_prediction(state, game_type)
        if games:
            games_by_state[state] = games
    
    if not games_by_state:
        return jsonify({'error': f'No {game_type} games found', 'db_mode': get_db_mode()}), 404
    
    # Step 1: Get all draws in the user's selected date range (seed draws)
    seed_draws = []
    seen_seeds = set()  # Track unique seed draws
    
    for state, games in games_by_state.items():
        query = {
            'state_name': state,
            'game_name': {'$in': games},
            'date': {'$gte': start_date, '$lt': end_date + timedelta(days=1)}
        }
        draws = list(collection.find(query))
        for d in draws:
            nums = parse_numbers(d.get('numbers', '[]'))
            if len(nums) == num_digits:
                tod = d.get('tod', '')
                if tod_filter != 'All' and tod.lower() != tod_filter.lower():
                    continue
                
                # Create unique key to prevent duplicates
                seed_key = (d['date'].strftime('%Y-%m-%d'), state, ''.join(nums), tod)
                if seed_key in seen_seeds:
                    continue
                seen_seeds.add(seed_key)
                
                seed_draws.append({
                    'date': d['date'],
                    'value': ''.join(nums),
                    'normalized': get_sorted_value(nums).replace('-', ''),
                    'state': d.get('state_name', ''),
                    'tod': tod,
                    'game': d.get('game_name', ''),
                    'digits_sum': sum(int(n) for n in nums)
                })
    
    if not seed_draws:
        return jsonify({
            'error': 'No draws found in selected date range',
            'db_mode': get_db_mode()
        }), 404
    
    # Get unique normalized numbers from seed draws
    seed_by_norm = {}
    for sd in seed_draws:
        norm = sd['normalized']
        if norm not in seed_by_norm:
            seed_by_norm[norm] = []
        seed_by_norm[norm].append(sd)
    
    past_winners = list(seed_by_norm.keys())
    
    # Step 2: For each seed normalized number, find ALL historical occurrences
    all_historical = []
    
    # Build a lookup of all draws by normalized value for efficiency
    all_draws_query = {}
    all_state_games = []
    for state, games in games_by_state.items():
        for game in games:
            all_state_games.append({'state_name': state, 'game_name': game})
    
    if all_state_games:
        all_draws_query['$or'] = all_state_games
    
    all_draws = list(collection.find(all_draws_query).sort('date', 1))
    
    # Index by normalized value - deduplicate by date+state+value
    draws_by_norm = {}
    seen_draws = set()  # Track unique draws to prevent duplicates
    
    for d in all_draws:
        nums = parse_numbers(d.get('numbers', '[]'))
        if len(nums) != num_digits:
            continue
        
        # Create unique key to prevent duplicates
        draw_key = (d['date'].strftime('%Y-%m-%d'), d.get('state_name', ''), ''.join(nums), d.get('tod', ''))
        if draw_key in seen_draws:
            continue
        seen_draws.add(draw_key)
        
        norm = get_sorted_value(nums).replace('-', '')
        if norm not in draws_by_norm:
            draws_by_norm[norm] = []
        draws_by_norm[norm].append({
            'date': d['date'],
            'value': ''.join(nums),
            'normalized': norm,
            'state': d.get('state_name', ''),
            'tod': d.get('tod', ''),
            'game': d.get('game_name', ''),
            'digits_sum': sum(int(n) for n in nums)
        })
    
    # Count total times drawn for each normalized number
    times_drawn = {norm: len(draws) for norm, draws in draws_by_norm.items()}
    
    # Build the results table
    results = []
    for norm, seed_list in seed_by_norm.items():
        historical_draws = draws_by_norm.get(norm, [])
        hit_count = len(historical_draws)
        
        for hist in historical_draws:
            # For each seed draw that matches this norm
            for seed in seed_list:
                date_diff = (seed['date'] - hist['date']).days
                
                # Calculate delta sums
                delta_sums = abs(seed['digits_sum'] - hist['digits_sum'])
                
                results.append({
                    'date': hist['date'].strftime('%Y-%m-%d'),
                    'value': hist['value'],
                    'norm': hist['normalized'],
                    'state': hist['state'],
                    'tod': hist['tod'],
                    'group': hist['date'].month,
                    'hit_count': hit_count,
                    'hit_ratio': round(hit_count / max(times_drawn.get(norm, 1), 1) * 100) if times_drawn else 0,
                    'repeat': len([h for h in historical_draws if h['value'] == hist['value']]),
                    'month': hist['date'].strftime('%Y-%m'),
                    'input_date': seed['date'].strftime('%Y-%m-%d'),
                    'perm': seed['value'],
                    'state2': seed['state'],
                    'tod2': seed['tod'],
                    'date_diff': date_diff,
                    'sums': hist['digits_sum'],
                    'td': times_drawn.get(norm, 0),
                    'delta_sums_td': delta_sums,
                    'sdt': 'D' if delta_sums <= 10 else 'S'
                })
    
    # Sort by date descending
    results.sort(key=lambda x: (x['input_date'], x['date']), reverse=True)
    
    return jsonify({
        'game_type': game_type,
        'date_range': f"{start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}",
        'states': states,
        'past_winners': sorted(past_winners),
        'total_seed_draws': len(seed_draws),
        'total_historical_matches': len(results),
        'draws': results[:5000],  # Limit to prevent huge responses
        'db_mode': get_db_mode()
    })


# =============================================================================
# TD LOOKUP — Times Drawn for normalized numbers
# =============================================================================

@app.route('/api/td/lookup', methods=['POST'])
def td_lookup():
    """
    Look up Times Drawn (TD) for a list of normalized numbers.
    TD = how many times this normalized number has been drawn in a specific state.
    
    Request body:
        candidates: list of normalized strings, e.g. ["1288", "3556", "0199"]
        state: state name (REQUIRED for accurate TD)
        game_type: pick4 or pick5 (default: pick4)
    
    Returns:
        td: {normalized: count, ...}
    """
    collection = get_collection()
    data = request.json
    
    candidates = data.get('candidates', [])
    state = data.get('state', 'Florida')
    game_type = data.get('game_type', 'pick4').lower()
    
    if not candidates:
        return jsonify({'error': 'No candidates provided'}), 400
    
    # Cap at 500 to prevent abuse
    candidates = candidates[:500]
    
    num_digits = {'pick2': 2, 'pick3': 3, 'pick4': 4, 'pick5': 5}.get(game_type, 4)
    
    # Get valid games for THIS state only
    games = get_games_for_prediction(state, game_type)
    if not games:
        return jsonify({'error': f'No {game_type} games found for {state}'}), 404
    
    # Build TD map — scan all draws for this state+game once, count ALL normalized values
    # Then filter to requested candidates
    full_td_map = {}
    cand_set = set(c.replace('-', '') for c in candidates)
    
    # Single query: get ALL draws for this state+game
    all_query = {
        'state_name': state,
        'game_name': {'$in': games}
    }
    
    all_draws = list(collection.find(all_query))
    
    for d in all_draws:
        nums = parse_numbers(d.get('numbers', '[]'))
        if len(nums) != num_digits:
            continue
        try:
            norm = ''.join(sorted(nums, key=lambda x: int(x)))
        except (ValueError, TypeError):
            continue
        # Only count if it's in our candidate set (saves memory)
        if norm in cand_set:
            full_td_map[norm] = full_td_map.get(norm, 0) + 1
    
    # Build result: requested candidates with their TD (0 if never drawn)
    td_map = {}
    for c in candidates:
        clean = c.replace('-', '')
        td_map[clean] = full_td_map.get(clean, 0)
    
    return jsonify({
        'game_type': game_type,
        'state': state,
        'count': len(td_map),
        'total_draws_scanned': len(all_draws),
        'td': td_map,
        'db_mode': get_db_mode()
    })
    
    return jsonify({
        'game_type': game_type,
        'state': state or 'All',
        'count': len(td_map),
        'td': td_map,
        'db_mode': get_db_mode()
    })


# =============================================================================
# MAIN
# =============================================================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    print(f"\n{'='*60}")
    print("LOTTERY PREDICTION APP")
    print(f"{'='*60}")
    print(f"Running on: http://localhost:{port}")
    print(f"DB Mode: {DEFAULT_DB_MODE}")
    print(f"{'='*60}\n")
    app.run(debug=True, host='0.0.0.0', port=port)
