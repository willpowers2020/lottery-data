from flask import Flask, render_template, jsonify, request
from pymongo import MongoClient
import os
import re
import json
from datetime import datetime, timedelta
from collections import Counter

app = Flask(__name__)

MONGO_URL = os.environ.get('MONGO_URL', 'mongodb+srv://willpowers2026:dFUATeYtHrP87gPk@cluster0.nmujtyo.mongodb.net/')
client = MongoClient(MONGO_URL)
db = client['mylottodata']
collection = db['lotterypost']

OUTLIERS = {
    ('Nebraska', 'Pick 5'): 'cash5',
}

def get_game_type(game_name, state_name=''):
    name = game_name.lower()
    state = state_name
    
    if (state, game_name) in OUTLIERS:
        return OUTLIERS[(state, game_name)]
    
    if any(x in name for x in ['cash 5', 'cash5', 'fantasy 5', 'fantasy5', 'take 5', 'take5', 'match 5', 'lotto 5']):
        return 'cash5'
    if any(x in name for x in ['pick 2', 'pick2', 'dc-2', 'dc2', 'cash 2', 'daily 2', 'play 2']):
        return 'pick2'
    if any(x in name for x in ['pick 3', 'pick3', 'dc-3', 'dc3', 'cash 3', 'cash3', 'daily 3', 'daily3', 'play 3', 'play3', 'numbers game', 'tri-state pick 3']):
        return 'pick3'
    if any(x in name for x in ['pick 4', 'pick4', 'dc-4', 'dc4', 'cash 4', 'cash4', 'daily 4', 'daily4', 'play 4', 'play4', 'win 4', 'win4', 'tri-state pick 4']):
        return 'pick4'
    if any(x in name for x in ['pick 5', 'pick5', 'dc-5', 'dc5', 'daily 5', 'daily5', 'play 5', 'play5', 'georgia five']):
        return 'pick5'
    return None

def normalize_tod(tod_field, game_name=''):
    tod = (tod_field or '').lower().strip()
    name = (game_name or '').lower()
    
    if tod in ['evening', 'night', 'noche', 'night owl']:
        return 'Evening'
    if tod in ['midday', 'matinee', 'daytime', 'día']:
        return 'Midday'
    if tod in ['day']:
        return 'Day'
    if tod in ['morning', 'early bird']:
        return 'Morning'
    if tod in ['7pm', '9pm', '10pm', '7:50pm']:
        return 'Evening'
    if tod in ['1pm', '2pm', '4pm', '1:50pm']:
        return 'Midday'
    
    if not tod:
        if any(x in name for x in ['evening', 'night', 'noche']):
            return 'Evening'
        if any(x in name for x in ['midday', 'mid-day']):
            return 'Midday'
        if any(x in name for x in ['morning']):
            return 'Morning'
        if ' day' in name or '-day' in name:
            return 'Day'
        if '7:50pm' in name:
            return 'Evening'
        if '1:50pm' in name:
            return 'Midday'
    return ''

def parse_numbers(numbers_str):
    try:
        nums = json.loads(numbers_str)
        return [str(n) for n in nums]
    except:
        return []

def get_sorted_value(nums):
    """Consistent sorted value calculation"""
    if not nums:
        return ''
    # Sort as integers for single digits, as strings for multi-digit
    try:
        return '-'.join(sorted(nums, key=lambda x: int(x)))
    except:
        return '-'.join(sorted(nums))

def get_matching_game_pairs(game_id, country):
    """Get list of (state, game) pairs that match the query"""
    if game_id.startswith('ALL_'):
        game_type = game_id.replace('ALL_', '')
        base_q = {'country': country} if country != 'all' else {}
        pipeline = [
            {'$match': base_q if base_q else {}},
            {'$group': {'_id': {'game': '$game_name', 'state': '$state_name'}}}
        ]
        results = list(collection.aggregate(pipeline))
        return [(r['_id']['state'], r['_id']['game']) for r in results 
                if get_game_type(r['_id']['game'], r['_id']['state']) == game_type]
    
    elif '|ALL_' in game_id:
        parts = game_id.split('|')
        cnt, state, game_type_str = parts[0], parts[1], parts[2]
        game_type = game_type_str.replace('ALL_', '')
        query = {'state_name': state}
        if cnt != 'all':
            query['country'] = cnt
        all_games = collection.distinct('game_name', query)
        return [(state, g) for g in all_games if get_game_type(g, state) == game_type]
    
    elif '|' in game_id:
        parts = game_id.split('|')
        if len(parts) == 3:
            return [(parts[1], parts[2])]
    
    return []

def build_game_query(game_id, country, base_query=None):
    query = base_query.copy() if base_query else {}
    
    if country != 'all':
        query['country'] = country
    
    pairs = get_matching_game_pairs(game_id, country)
    
    if pairs:
        if len(pairs) == 1:
            query['state_name'] = pairs[0][0]
            query['game_name'] = pairs[0][1]
        else:
            or_conditions = [{'state_name': state, 'game_name': game} for state, game in pairs]
            query['$or'] = or_conditions
    
    return query

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/countries')
def get_countries():
    countries = collection.distinct('country')
    countries = sorted([c for c in countries if c])
    return jsonify([{'id': c, 'name': c} for c in countries])

@app.route('/api/states/<country>')
def get_states(country):
    if country == 'all':
        states = collection.distinct('state_name')
    else:
        states = collection.distinct('state_name', {'country': country})
    states = sorted([s for s in states if s])
    return jsonify([{'id': s, 'name': s} for s in states])

@app.route('/api/games/<country>/<state_id>')
def get_games(country, state_id):
    base_query = {}
    if country != 'all':
        base_query['country'] = country
    
    if state_id == 'all':
        pipeline = [
            {'$match': base_query},
            {'$group': {'_id': {'game': '$game_name', 'state': '$state_name', 'country': '$country'}}},
            {'$sort': {'_id.game': 1, '_id.state': 1}}
        ]
        results = list(collection.aggregate(pipeline))
        
        by_type = {'pick2': [], 'pick3': [], 'pick4': [], 'pick5': [], 'cash5': []}
        for r in results:
            game = r['_id']['game']
            state = r['_id']['state']
            cnt = r['_id'].get('country', '')
            game_type = get_game_type(game, state)
            if game_type:
                by_type[game_type].append({'game': game, 'state': state, 'country': cnt})
        
        result = []
        type_names = {
            'pick2': 'Pick 2 (0-9)',
            'pick3': 'Pick 3 (0-9)',
            'pick4': 'Pick 4 (0-9)',
            'pick5': 'Pick 5 (0-9)',
            'cash5': 'Cash 5 / Fantasy 5'
        }
        
        for game_type in ['pick2', 'pick3', 'pick4', 'pick5', 'cash5']:
            games_list = by_type[game_type]
            if games_list:
                result.append({
                    'id': f"ALL_{game_type}",
                    'name': f"{type_names[game_type]} (All - {len(games_list)} game/state combos)",
                    'is_group': True,
                    'game_type': game_type
                })
                for g in sorted(games_list, key=lambda x: (x['country'], x['state'], x['game'])):
                    display = f"{g['country']} - {g['state']} - {g['game']}" if country == 'all' else f"{g['state']} - {g['game']}"
                    result.append({
                        'id': f"{g['country']}|{g['state']}|{g['game']}",
                        'name': display,
                        'is_group': False,
                        'game_type': game_type
                    })
        
        return jsonify(result)
    
    else:
        query = {'state_name': state_id}
        if country != 'all':
            query['country'] = country
        games = collection.distinct('game_name', query)
        
        grouped = {}
        type_names = {
            'pick2': 'Pick 2 (0-9)',
            'pick3': 'Pick 3 (0-9)',
            'pick4': 'Pick 4 (0-9)',
            'pick5': 'Pick 5 (0-9)',
            'cash5': 'Cash 5 / Fantasy 5'
        }
        
        for game in games:
            game_type = get_game_type(game, state_id)
            if game_type:
                if game_type not in grouped:
                    grouped[game_type] = []
                grouped[game_type].append(game)
        
        result = []
        for game_type in ['pick2', 'pick3', 'pick4', 'pick5', 'cash5']:
            if game_type not in grouped:
                continue
            games_list = sorted(grouped[game_type])
            if len(games_list) > 1:
                result.append({
                    'id': f"{country}|{state_id}|ALL_{game_type}",
                    'name': f"{type_names[game_type]} (All)",
                    'is_group': True
                })
            for g in games_list:
                result.append({
                    'id': f"{country}|{state_id}|{g}",
                    'name': g,
                    'is_group': False
                })
        
        return jsonify(result)

@app.route('/api/game_info', methods=['POST'])
def get_game_info():
    data = request.json
    game_id = data.get('game_ids', '')
    country = data.get('country', 'all')
    
    query = build_game_query(game_id, country)
    
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
    country = data.get('country', 'all')
    start_date = datetime.strptime(data.get('start_date'), '%Y-%m-%d')
    end_date = datetime.strptime(data.get('end_date'), '%Y-%m-%d') + timedelta(days=1)
    
    # Get matching game pairs for this query
    pairs = get_matching_game_pairs(game_id, country)
    
    if not pairs:
        return jsonify([])
    
    # Build query for date range
    base_query = {'date': {'$gte': start_date, '$lt': end_date}}
    if country != 'all':
        base_query['country'] = country
    
    if len(pairs) == 1:
        base_query['state_name'] = pairs[0][0]
        base_query['game_name'] = pairs[0][1]
    else:
        base_query['$or'] = [{'state_name': s, 'game_name': g} for s, g in pairs]
    
    draws = list(collection.find(base_query).sort('date', -1).limit(1000))
    
    # Calculate TD: count sorted values across ALL historical data for this query scope
    td_query = {}
    if country != 'all':
        td_query['country'] = country
    
    if len(pairs) == 1:
        td_query['state_name'] = pairs[0][0]
        td_query['game_name'] = pairs[0][1]
    else:
        td_query['$or'] = [{'state_name': s, 'game_name': g} for s, g in pairs]
    
    # Use aggregation to count sorted values efficiently
    td_pipeline = [
        {'$match': td_query},
        {'$project': {'numbers': 1}},
    ]
    all_for_td = list(collection.aggregate(td_pipeline, allowDiskUse=True))
    
    # Count sorted values
    td_counter = Counter()
    for d in all_for_td:
        nums = parse_numbers(d.get('numbers', '[]'))
        if nums:
            sv = get_sorted_value(nums)
            td_counter[sv] += 1
    
    # Process draws
    result = []
    seen = set()
    
    for d in draws:
        nums = parse_numbers(d.get('numbers', '[]'))
        if not nums:
            continue
        
        value = '-'.join(nums)
        sorted_value = get_sorted_value(nums)
        sums = sum(int(n) for n in nums if n.isdigit())
        tod = normalize_tod(d.get('tod', ''), d.get('game_name', ''))
        
        key = (d['date'].strftime('%Y-%m-%d'), d.get('country', ''), d.get('state_name', ''), d['game_name'], value)
        if key in seen:
            continue
        seen.add(key)
        
        result.append({
            'draw_date': d['date'].strftime('%Y-%m-%d'),
            'country': d.get('country', ''),
            'state_name': d.get('state_name', ''),
            'game_name': d['game_name'],
            'tod': tod,
            'value': value,
            'sorted_value': sorted_value,
            'sums': sums,
            'td': td_counter.get(sorted_value, 0)
        })
    
    return jsonify(result)

@app.route('/api/analysis', methods=['POST'])
def get_analysis():
    data = request.json
    game_id = data.get('game_ids', '')
    country = data.get('country', 'all')
    start_date = datetime.strptime(data.get('start_date'), '%Y-%m-%d')
    end_date = datetime.strptime(data.get('end_date'), '%Y-%m-%d') + timedelta(days=1)
    
    base_query = {'date': {'$gte': start_date, '$lt': end_date}}
    query = build_game_query(game_id, country, base_query)
    
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
        
        for n in nums:
            if n.isdigit() and len(n) == 1:
                digit_freq[n] = digit_freq.get(n, 0) + 1
        
        if all(n.isdigit() and len(n) == 1 for n in nums):
            s = sum(int(n) for n in nums)
            sum_freq[s] = sum_freq.get(s, 0) + 1
            p = get_sorted_value(nums)
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
