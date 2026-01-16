from flask import Flask, render_template, jsonify, request
import psycopg2
from psycopg2.extras import RealDictCursor
import os
import re
from datetime import datetime

app = Flask(__name__)

DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://postgres.lewvjrlflatexlcndefi:jx4wdz7vQ62ENoCD@aws-1-us-east-1.pooler.supabase.com:5432/postgres')

def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/states')
def get_states():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM states ORDER BY name")
    states = cur.fetchall()
    conn.close()
    return jsonify(states)

@app.route('/api/games/<int:state_id>')
def get_games(state_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, name FROM games 
        WHERE state_id = %s AND active = true 
        ORDER BY name
    """, (state_id,))
    games = cur.fetchall()
    conn.close()
    
    # Group games by base name
    grouped = {}
    for g in games:
        name = g['name']
        # Extract base name (e.g., "Pick 3" from "Pick 3 Midday")
        base = re.sub(r'\s*(Midday|Evening|Day|Night|Morning).*$', '', name, flags=re.IGNORECASE).strip()
        
        if base not in grouped:
            grouped[base] = {'base': base, 'games': []}
        grouped[base]['games'].append({'id': g['id'], 'name': name})
    
    # Build response with grouped options
    result = []
    for base, data in sorted(grouped.items()):
        if len(data['games']) > 1:
            # Add "All" option for this game type
            ids = ','.join(str(g['id']) for g in data['games'])
            result.append({
                'id': ids,
                'name': f"{base} (All)",
                'is_group': True
            })
        # Add individual games
        for g in data['games']:
            result.append({
                'id': str(g['id']),
                'name': g['name'],
                'is_group': False
            })
    
    return jsonify(result)

@app.route('/api/game_info', methods=['POST'])
def get_game_info():
    data = request.json
    game_ids = data.get('game_ids', '').split(',')
    game_ids = [int(g) for g in game_ids if g.isdigit()]
    
    if not game_ids:
        return jsonify({'error': 'No game IDs'}), 400
    
    conn = get_db()
    cur = conn.cursor()
    
    placeholders = ','.join(['%s'] * len(game_ids))
    cur.execute(f"""
        SELECT MIN(draw_date) as min_date, MAX(draw_date) as max_date, COUNT(*) as total
        FROM draws WHERE game_id IN ({placeholders})
    """, game_ids)
    info = cur.fetchone()
    conn.close()
    
    return jsonify({
        'min_date': info['min_date'].isoformat() if info['min_date'] else None,
        'max_date': info['max_date'].isoformat() if info['max_date'] else None,
        'total': info['total']
    })

@app.route('/api/draws', methods=['POST'])
def get_draws():
    data = request.json
    game_ids = data.get('game_ids', '').split(',')
    game_ids = [int(g) for g in game_ids if g.isdigit()]
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    
    if not game_ids:
        return jsonify([])
    
    conn = get_db()
    cur = conn.cursor()
    
    placeholders = ','.join(['%s'] * len(game_ids))
    
    # Use DISTINCT to avoid duplicates
    query = f"""
        SELECT DISTINCT d.draw_date, d.value, d.sorted_value, d.sums, g.name as game_name
        FROM draws d
        JOIN games g ON d.game_id = g.id
        WHERE d.game_id IN ({placeholders})
        AND d.draw_date BETWEEN %s AND %s
        ORDER BY d.draw_date DESC, g.name
        LIMIT 500
    """
    params = game_ids + [start_date, end_date]
    
    cur.execute(query, params)
    draws = cur.fetchall()
    conn.close()
    
    for d in draws:
        d['draw_date'] = d['draw_date'].isoformat()
    
    return jsonify(draws)

@app.route('/api/analysis', methods=['POST'])
def get_analysis():
    data = request.json
    game_ids = data.get('game_ids', '').split(',')
    game_ids = [int(g) for g in game_ids if g.isdigit()]
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    
    if not game_ids:
        return jsonify({'error': 'No game IDs'}), 400
    
    conn = get_db()
    cur = conn.cursor()
    
    placeholders = ','.join(['%s'] * len(game_ids))
    
    # Use DISTINCT to avoid counting duplicates
    cur.execute(f"""
        SELECT DISTINCT draw_date, value, sorted_value, sums FROM draws
        WHERE game_id IN ({placeholders}) AND draw_date BETWEEN %s AND %s
    """, game_ids + [start_date, end_date])
    draws = cur.fetchall()
    
    digit_freq = {str(i): 0 for i in range(10)}
    sum_freq = {}
    pattern_freq = {}
    
    for d in draws:
        for digit in d['value'].replace('-', ''):
            digit_freq[digit] = digit_freq.get(digit, 0) + 1
        s = d['sums']
        sum_freq[s] = sum_freq.get(s, 0) + 1
        p = d['sorted_value']
        pattern_freq[p] = pattern_freq.get(p, 0) + 1
    
    top_patterns = sorted(pattern_freq.items(), key=lambda x: x[1], reverse=True)[:20]
    top_sums = sorted(sum_freq.items(), key=lambda x: x[1], reverse=True)[:10]
    sorted_digits = sorted(digit_freq.items(), key=lambda x: x[1], reverse=True)
    hot = sorted_digits[:5]
    cold = sorted_digits[-5:]
    
    conn.close()
    
    return jsonify({
        'digit_frequency': digit_freq,
        'hot_digits': hot,
        'cold_digits': cold,
        'top_patterns': top_patterns,
        'top_sums': top_sums,
        'total_draws': len(draws)
    })

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
