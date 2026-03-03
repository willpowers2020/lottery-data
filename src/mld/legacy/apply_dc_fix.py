"""
═══════════════════════════════════════════════════════════════
  PATCH: app.py — Fix Washington DC name aliasing
═══════════════════════════════════════════════════════════════

Apply these 2 changes to app.py:

CHANGE 1: Add normalize_state_name() function after line 68 (after QUERY_COST_CONFIG)
CHANGE 2: Add the function call in get_games_for_prediction()
CHANGE 3: Update the Pick 5 states lists

Alternatively, just run: python apply_dc_fix.py
"""

# ════════════════════════════════════════════
# To apply automatically, run this script:
# ════════════════════════════════════════════

import re

def apply_fix():
    with open('app.py', 'r') as f:
        content = f.read()
    
    # ── CHANGE 1: Add normalize_state_name function ──
    # Insert after the imports section, before QUERY_COST_CONFIG
    normalizer_code = '''
# =============================================================================
# STATE NAME NORMALIZATION
# =============================================================================

STATE_NAME_ALIASES = {
    'Washington DC': 'Washington, D.C.',
    'washington dc': 'Washington, D.C.',
    'Washington D.C.': 'Washington, D.C.',
    'Washington D.C': 'Washington, D.C.',
    'DC': 'Washington, D.C.',
}

def normalize_state_name(state):
    """Normalize state name variants to canonical form used in MongoDB."""
    if not state:
        return state
    return STATE_NAME_ALIASES.get(state, state)

'''
    
    # Insert before QUERY_COST_CONFIG
    if 'normalize_state_name' not in content:
        content = content.replace(
            '# =============================================================================\n# QUERY BILLING & COST ESTIMATION',
            normalizer_code + '# =============================================================================\n# QUERY BILLING & COST ESTIMATION'
        )
        print("✅ Added normalize_state_name() function")
    else:
        print("⏭️  normalize_state_name() already exists")
    
    # ── CHANGE 2: Add normalization in get_games_for_prediction ──
    old_ggfp = "def get_games_for_prediction(state, game_type):\n    collection = get_collection()\n    all_games = collection.distinct('game_name', {'state_name': state})"
    new_ggfp = "def get_games_for_prediction(state, game_type):\n    state = normalize_state_name(state)\n    collection = get_collection()\n    all_games = collection.distinct('game_name', {'state_name': state})"
    
    if 'state = normalize_state_name(state)' not in content.split('def get_games_for_prediction')[1][:200] if 'def get_games_for_prediction' in content else True:
        content = content.replace(old_ggfp, new_ggfp)
        print("✅ Added normalization to get_games_for_prediction()")
    else:
        print("⏭️  get_games_for_prediction() already normalized")
    
    # ── CHANGE 3: Add normalization to all API endpoints that receive state ──
    # Rather than patching 14 endpoints, we add it to get_collection query transform
    # Add normalization in MongoOptimizedAdapter._transform_query
    old_transform = """            if key == 'state_name':
                # Can query by state_name (full name) or state (code)
                mongo_query['state_name'] = value"""
    new_transform = """            if key == 'state_name':
                # Can query by state_name (full name) or state (code)
                # Normalize aliases like "Washington DC" → "Washington, D.C."
                mongo_query['state_name'] = normalize_state_name(value) if isinstance(value, str) else value"""
    
    if 'normalize_state_name(value)' not in content:
        content = content.replace(old_transform, new_transform)
        print("✅ Added normalization to MongoOptimizedAdapter._transform_query()")
    else:
        print("⏭️  _transform_query() already normalized")
    
    # ── CHANGE 4: Update PICK5_STATES hardcoded lists ──
    content = content.replace(
        "'Pennsylvania', 'Georgia', 'Washington DC', 'Louisiana', 'Germany'",
        "'Pennsylvania', 'Georgia', 'Washington, D.C.', 'Louisiana', 'Germany'"
    )
    print("✅ Updated hardcoded Pick 5 state lists")
    
    # Write back
    with open('app.py', 'w') as f:
        f.write(content)
    
    print("\n✅ All patches applied to app.py")
    print("   Restart Flask to apply: python app.py")


if __name__ == '__main__':
    apply_fix()
