from flask import Flask, render_template, jsonify, request
from pymongo import MongoClient
import os
import re
import json
from datetime import datetime, timedelta

app = Flask(__name__)

MONGO_URL = os.environ.get('MONGO_URL', 'mongodb+srv://willpowers:Ilovemymom2@cluster0.nmujtyo.mongodb.net/')
client = MongoClient(MONGO_URL)
db = client['mylottodata']
collection = db['lotterypost']

def get_digit_count(game_name):
    """Determine if game is Pick 2, 3, 4, or 5"""
    name = game_name.lower()
    if any(x in name for x in ['pick 2', 'dc-2', 'cash 2', 'daily 2', 'play 2']):
        return 2
    if any(x in name for x in ['pick 3', 'dc-3', 'cash 3', 'daily 3', 'play 3', 'numbers game', 'tri-state pick 3']):
        return 3
    if any(x in name for x in ['pick 4', 'dc-4', 'cash 4', 'daily 4', 'play 4', 'win 4', 'tri-state pick 4']):
        return 4
    if any(x in name for x in ['pick 5', 'dc-5', 'cash 5', 'daily 5', 'play 5', 'georgia five', 'fantasy 5']):
        return 5
    return None

def parse_numbers(numbers_str):
    """Parse numbers from JSON string like '["0", "6", "1"]'"""
    try:
        nums = json.loads(numbers_str)
        return [str(n) for n in nums]
    except:
        return []

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/states')
def get_states():
    # Get distinct US states
    states = collection.distinct('state_name', {'country': 'USA'})
    states = sorted([s for s in states if s])
    return jsonify([{'id': s, 'name': s} for s in states])

@app.route('/api/games/<state_id>')
def get_games(state_id):
    if state_id == 'all':
        # Get all Pick 2-5 games across all US states
        pipeline = [
            {'$match': {'country': 'USA'}},
            {'$group': {'_id': {'game': '$game_name', 'state': '$state_name'}}},
            {'$sort': {'_id.game': 1, '_id.state': 1}}
        ]
        results = list(collection.aggregate(pipeline))
        
        # Group by digit count
        by_digits = {2: [], 3: [], 4: [], 5: []}
        for r in results:
            game = r['_id']['game']
            state = r['_id']['state']
            digits = get_digit_count(game)
            if digits:
                by_digits[digits].append({'game': game, 'state': state})
        
        result = []
        digit_names = {2: 'Pick 2', 3: 'Pick 3', 4: 'Pick 4', 5: 'Pick 5'}
        
        for digits in [2, 3, 4, 5]:
            games_list = by_digits[digits]
            if games_list:
                # Create grouped ID (game names joined)
                unique_games = list(set(g['game'] for g in games_list))
                result.append({
                    'id': f"ALL_{digits}",
                    'name': f"{digit_names[digits]} (All States - {len(games_list)} game/state combos)",
                    'is_group': True,
                    'digits': digits
                })
                for g in sorted(games_list, key=lambda x: (x['state'], x['game'])):
                    result.append({
                        'id': f"{g['state']}|{g['game']}",
                        'name': f"{g['state']} - {g['game']}",
                        'is_group': False,
                        'digits': digits
                    })
        
        return jsonify(result)
    
    else:
        # Single state - get games
        games = collection.distinct('game_name', {'state_name': state_id, 'country': 'USA'})
        
        # Group by digit count
        grouped = {}
        for game in games:
            digits = get_digit_count(game)
            if digits:
                base = f"Pick {digits}"
                if base not in grouped:
                    grouped[base] = []
                grouped[base].append(game)
        
        result = []
        for base in sorted(grouped.keys()):
            games_list = sorted(grouped[base])
            if len(games_list) > 1:
                result.append({
                    'id': f"{state_id}|ALL_{base.replace(' ', '')}",
                    'name': f"{base} (All)",
                    'is_group': True
                })
            for g in games_list:
                result.append({
                    'id': f"{state_id}|{g}",
                    'name': g,
                    'is_group': False
                })
        
        return jsonify(result)

@app.route('/api/game_info', methods=['POST'])
def get_game_info():
    data = request.json
    game_id = data.get('game_ids', '')
    
    # Build query based on game_id format
    query = {'country': 'USA'}
    
    if game_id.startswith('ALL_'):
        # All states for a digit count
        digits = int(game_id.replace('ALL_', ''))
        # Get all games matching this digit count
        all_games = collection.distinct('game_name', {'country': 'USA'})
        matching = [g for g in all_games if get_digit_count(g) == digits]
        query['game_name'] = {'$in': matching}
    elif '|ALL_' in game_id:
        # All games of a type in one state
        state, game_type = game_id.split('|ALL_')
        digits = int(game_type.replace('Pick', ''))
        all_games = collection.distinct('game_name', {'state_name': state, 'country': 'USA'})
        matching = [g for g in all_games if get_digit_count(g) == digits]
        query['state_name'] = state
        query['game_name'] = {'$in': matching}
    elif '|' in game_id:
        # Specific state and game
        state, game = game_id.split('|', 1)
        query['state_name'] = state
        query['game_name'] = game
    
    # Get date range
    pipeline = [
        {'$match': query},
        {'$group': {
            '_id': None,
            'min_date': {'$min': '$date'},
            'max_date': {'$max': '$date'},
            'total': {'$sum': 1}
        }}
    ]
    result = list(collection.aggregate(pipeline))
    
    if result:
        return jsonify({
            'min_date': result[0]['min_date'].strftime('%Y-%m-%d') if result[0]['min_date'] else None,
            'max_date': result[0]['max_date'].strftime('%Y-%m-%d') if result[0]['max_date'] else None,
            'total': result[0]['total']
        })
    return jsonify({'min_date': None, 'max_date': None, 'total': 0})

@app.route('/api/draws', methods=['POST'])
def get_draws():
    data = request.json
    game_id = data.get('game_ids', '')
    start_date = datetime.strptime(data.get('start_date'), '%Y-%m-%d')
    end_date = datetime.strptime(data.get('end_date'), '%Y-%m-%d') + timedelta(days=1)
    
    # Build query
    query = {
        'country': 'USA',
        'date': {'$gte': start_date, '$lt': end_date}
    }
    
    if game_id.startswith('ALL_'):
        digits = int(game_id.replace('ALL_', ''))
        all_games = collection.distinct('game_name', {'country': 'USA'})
        matching = [g for g in all_games if get_digit_count(g) == digits]
        query['game_name'] = {'$in': matching}
    elif '|ALL_' in game_id:
        state, game_type = game_id.split('|ALL_')
        digits = int(game_type.replace('Pick', ''))
        all_games = collection.distinct('game_name', {'state_name': state, 'country': 'USA'})
        matching = [g for g in all_games if get_digit_count(g) == digits]
        query['state_name'] = state
        query['game_name'] = {'$in': matching}
    elif '|' in game_id:
        state, game = game_id.split('|', 1)
        query['state_name'] = state
        query['game_name'] = game
    
    # Fetch draws
    draws = list(collection.find(query).sort('date', -1).limit(1000))
    
    result = []
    seen = set()
    for d in draws:
        nums = parse_numbers(d.get('numbers', '[]'))
        if not nums:
            continue
        
        value = '-'.join(nums)
        sorted_value = '-'.join(sorted(nums))
        sums = sum(int(n) for n in nums if n.isdigit())
        
        # Dedupe
        key = (d['date'].strftime('%Y-%m-%d'), d['state_name'], d['game_name'], value)
        if key in seen:
            continue
        seen.add(key)
        
        result.append({
            'draw_date': d['date'].strftime('%Y-%m-%d'),
            'state_name': d['state_name'],
            'game_name': d['game_name'],
            'value': value,
            'sorted_value': sorted_value,
            'sums': sums
        })
    
    return jsonify(result)

@app.route('/api/analysis', methods=['POST'])
def get_analysis():
    data = request.json
    game_id = data.get('game_ids', '')
    start_date = datetime.strptime(data.get('start_date'), '%Y-%m-%d')
    end_date = datetime.strptime(data.get('end_date'), '%Y-%m-%d') + timedelta(days=1)
    
    # Build query
    query = {
        'country': 'USA',
        'date': {'$gte': start_date, '$lt': end_date}
    }
    
    if game_id.startswith('ALL_'):
        digits = int(game_id.replace('ALL_', ''))
        all_games = collection.distinct('game_name', {'country': 'USA'})
        matching = [g for g in all_games if get_digit_count(g) == digits]
        query['game_name'] = {'$in': matching}
    elif '|ALL_' in game_id:
        state, game_type = game_id.split('|ALL_')
        digits = int(game_type.replace('Pick', ''))
        all_games = collection.distinct('game_name', {'state_name': state, 'country': 'USA'})
        matching = [g for g in all_games if get_digit_count(g) == digits]
        query['state_name'] = state
        query['game_name'] = {'$in': matching}
    elif '|' in game_id:
        state, game = game_id.split('|', 1)
        query['state_name'] = state
        query['game_name'] = game
    
    # Fetch and analyze
    draws = list(collection.find(query, {'numbers': 1}))
    
    digit_freq = {str(i): 0 for i in range(10)}
    sum_freq = {}
    pattern_freq = {}
    total = 0
    
    for d in draws:
        nums = parse_numbers(d.get('numbers', '[]'))
        if not nums or len(nums) < 2:
            continue
        
        total += 1
        
        # Count digits
        for n in nums:
            if n.isdigit() and len(n) == 1:
                digit_freq[n] = digit_freq.get(n, 0) + 1
        
        # Sums (only for single-digit numbers)
        if all(n.isdigit() and len(n) == 1 for n in nums):
            s = sum(int(n) for n in nums)
            sum_freq[s] = sum_freq.get(s, 0) + 1
            
            # Patterns (sorted)
            p = '-'.join(sorted(nums))
            pattern_freq[p] = pattern_freq.get(p, 0) + 1
    
    top_patterns = sorted(pattern_freq.items(), key=lambda x: x[1], reverse=True)[:20]
    top_sums = sorted(sum_freq.items(), key=lambda x: x[1], reverse=True)[:10]
    sorted_digits = sorted(digit_freq.items(), key=lambda x: x[1], reverse=True)
    hot = sorted_digits[:5]
    cold = sorted_digits[-5:]
    
    return jsonify({
        'digit_frequency': digit_freq,
        'hot_digits': hot,
        'cold_digits': cold,
        'top_patterns': top_patterns,
        'top_sums': top_sums,
        'total_draws': total
    })

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
