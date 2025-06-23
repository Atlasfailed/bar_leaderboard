from flask import Flask, jsonify, render_template
from flask_cors import CORS
import pandas as pd
import os
from datetime import datetime, timedelta
import numpy as np 
import math
import json

# --- Configuration ---
app = Flask(__name__)
CORS(app)

# --- Production/Development Environment Detection ---
# Check if running on PythonAnywhere or locally
PRODUCTION = os.environ.get('FLASK_ENV') == 'production'

# --- FIX: Set the base directory to the directory of the app.py file ---
# This ensures it finds the 'data' folder inside your project directory.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

LEADERBOARD_DATA_FILE   = os.path.join(BASE_DIR, 'data', 'final_leaderboard.parquet')
ISO_COUNTRIES_FILE      = os.path.join(BASE_DIR, 'data', 'iso_country.csv')
NATION_RANKINGS_FILE    = os.path.join(BASE_DIR, 'data', 'nation_rankings.parquet')
EFFICIENCY_ANALYSIS_FILE = os.path.join(BASE_DIR, 'data', 'efficiency_vs_speed_analysis_with_names.csv')
TEAM_ANALYSIS_FILE = os.path.join(BASE_DIR, 'data', 'roster_analysis_results.json')


# --- This file is required for the search functionality ---
PLAYER_CONTRIBUTIONS_FILE = os.path.join(BASE_DIR, 'data/player_contributions.parquet')


# --- Data Update Schedule Logic ---
def get_last_datamart_update():
    """
    Calculate the last datamart update time based on cron schedule: '0 10 * * 2,6'
    This means updates happen at 10:00 AM on Tuesdays (2) and Saturdays (6).
    """
    now = datetime.now()
    
    # Find the most recent Tuesday or Saturday at 10:00 AM
    days_back = 0
    while days_back <= 7:  # Look back up to a week
        check_date = now - timedelta(days=days_back)
        
        # Check if it's Tuesday (1) or Saturday (5) in Python's weekday system (Monday=0)
        if check_date.weekday() in [1, 5]:  # Tuesday=1, Saturday=5
            update_time = check_date.replace(hour=10, minute=0, second=0, microsecond=0)
            
            # Only use this time if it's in the past
            if update_time <= now:
                return update_time
        
        days_back += 1
    
    # Fallback: return a time from a week ago if nothing found
    fallback = now - timedelta(days=7)
    return fallback.replace(hour=10, minute=0, second=0, microsecond=0)


# --- Data Preprocessing for Performance ---
def preprocess_leaderboard_data(leaderboard_df):
    """Pre-process leaderboard data to create fast lookup tables."""
    processed = {}
    
    # Get unique combinations of leaderboard_id and game_type
    combinations = leaderboard_df[['leaderboard_id', 'game_type']].drop_duplicates()
    
    for _, row in combinations.iterrows():
        leaderboard_id = row['leaderboard_id']
        game_type = row['game_type']
        key = f"{leaderboard_id}_{game_type}"
        
        # Filter data for this combination
        filtered_df = leaderboard_df[
            (leaderboard_df['leaderboard_id'] == leaderboard_id) & 
            (leaderboard_df['game_type'] == game_type)
        ]
        
        # Get latest entry for each player (vectorized operation)
        if not filtered_df.empty:
            # Sort by start_time and get the last entry for each player
            latest_entries = filtered_df.sort_values('start_time').groupby('name').tail(1)
            
            # Convert to list of player dictionaries
            players = []
            for _, player in latest_entries.iterrows():
                players.append({
                    "name": player['name'],
                    "display_name": player['name'],
                    "leaderboard_rating": float(player['leaderboard_rating']),
                    "countryCode": player.get('countryCode', ''),
                    "user_id": int(player['user_id'])
                })
            
            # Sort by rating (descending) and add ranks
            players.sort(key=lambda x: x['leaderboard_rating'], reverse=True)
            for i, player in enumerate(players):
                player['rank'] = i + 1
            
            processed[key] = {
                "players": players,
                "total_players": len(players)
            }
    
    # Also create global leaderboards for each game type
    game_types = leaderboard_df['game_type'].unique()
    for game_type in game_types:
        key = f"global_{game_type}"
        
        # Filter by game type only
        filtered_df = leaderboard_df[leaderboard_df['game_type'] == game_type]
        
        if not filtered_df.empty:
            # Get latest entry for each player (vectorized operation)
            latest_entries = filtered_df.sort_values('start_time').groupby('name').tail(1)
            
            # Convert to list of player dictionaries
            players = []
            for _, player in latest_entries.iterrows():
                players.append({
                    "name": player['name'],
                    "display_name": player['name'],
                    "leaderboard_rating": float(player['leaderboard_rating']),
                    "countryCode": player.get('countryCode', ''),
                    "user_id": int(player['user_id'])
                })
            
            # Sort by rating (descending) and add ranks
            players.sort(key=lambda x: x['leaderboard_rating'], reverse=True)
            for i, player in enumerate(players):
                player['rank'] = i + 1
            
            processed[key] = {
                "players": players,
                "total_players": len(players)
            }
    
    return processed


# --- Data Loading ---
def load_data():
    """Loads and caches all necessary data files."""
    leaderboard_df, country_map, nation_rankings_df, last_updated, player_contributions_df = None, {}, None, "N/A", None
    processed_leaderboards = {}  # Cache for processed leaderboard data

    # Main leaderboard
    if os.path.exists(LEADERBOARD_DATA_FILE):
        try:
            leaderboard_df = pd.read_parquet(LEADERBOARD_DATA_FILE)
            
            # Calculate last updated time based on datamart cron schedule
            last_datamart_update = get_last_datamart_update()
            last_updated = last_datamart_update.strftime('%B %d, %Y at %H:%M UTC')
            print(f"Loaded {len(leaderboard_df)} player leaderboard records.")
            print(f"Data represents datamart update from: {last_updated}")
            
            # Pre-process leaderboard data for faster API responses
            print("Pre-processing leaderboard data for faster access...")
            processed_leaderboards = preprocess_leaderboard_data(leaderboard_df)
            print(f"Pre-processed {len(processed_leaderboards)} leaderboard combinations.")
        except Exception as e:
            print(f"ERROR loading player leaderboard data: {e}")

    # Country mapping
    if os.path.exists(ISO_COUNTRIES_FILE):
        try:
            countries_df = pd.read_csv(ISO_COUNTRIES_FILE)
            country_map = pd.Series(countries_df.name.values, index=countries_df['alpha-2'].str.strip()).to_dict()
            print(f"Loaded {len(country_map)} country mappings.")
        except Exception as e:
            print(f"ERROR loading country data: {e}")

    # Nation rankings
    if os.path.exists(NATION_RANKINGS_FILE):
        try:
            nation_rankings_df = pd.read_parquet(NATION_RANKINGS_FILE)
            print(f"Loaded {len(nation_rankings_df)} nation ranking records.")
        except Exception as e:
            print(f"ERROR loading nation ranking data: {e}")
    else:
        print(f"INFO: Nation ranking file not found at: {NATION_RANKINGS_FILE}")

    # Player contributions for search
    if os.path.exists(PLAYER_CONTRIBUTIONS_FILE):
        try:
            player_contributions_df = pd.read_parquet(PLAYER_CONTRIBUTIONS_FILE)
            print(f"Loaded {len(player_contributions_df)} player contribution records.")
        except Exception as e:
            print(f"ERROR loading player contributions data: {e}")
    else:
        print(f"INFO: Player contributions file not found at: {PLAYER_CONTRIBUTIONS_FILE}")

    return leaderboard_df, country_map, last_updated, nation_rankings_df, player_contributions_df, processed_leaderboards

# Load data on startup
leaderboard_df, country_name_map, last_updated_time, nation_rankings_df, player_contributions_df, processed_leaderboards_cache = load_data()


# --- API Endpoints ---
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/nation-rankings')
def nation_rankings_page():
    return render_template('nation_rankings.html')

@app.route('/efficiency-analysis')
def efficiency_analysis_page():
    return render_template('efficiency_analysis.html')

@app.route('/team-rankings')
def team_rankings_page():
    return render_template('team_rankings.html')




@app.route('/api/player-contributions/<game_type>')
def get_player_contributions(game_type):
    """Provides the full list of player contributions for a game type."""
    if player_contributions_df is None:
        return jsonify({"error": "Player contributions data not available. Please run 'nation_ranking_pipeline.py' again to generate it."}), 500

    game_type_str = game_type.replace('%20', ' ')
    filtered_df = player_contributions_df[player_contributions_df['game_type'] == game_type_str]
    
    cleaned_records = []
    for record in filtered_df.to_dict(orient='records'):
        cleaned_records.append({
            'name': record.get('name'),
            'country_name': record.get('country_name', record.get('countryCode')),
            'score': int(record.get('score', 0))
        })
        
    return jsonify(cleaned_records)


@app.route('/api/nation-rankings/<game_type>')
def get_nation_rankings(game_type):
    """Provides the weekly nation rankings for a specific game type."""
    if nation_rankings_df is None:
        return jsonify({"error": "Nation ranking data not available. Please run 'nation_ranking_pipeline.py' successfully first."}), 500

    game_type_str = game_type.replace('%20', ' ')
    filtered_df = nation_rankings_df[nation_rankings_df['game_type'] == game_type_str].copy()

    if filtered_df.empty:
        return jsonify([])

    records = filtered_df.to_dict(orient='records')
    
    # --- FIX: Rebuild records from scratch to ensure clean types for JSON serialization. ---
    # This is the most critical fix to handle numpy data types that jsonify cannot process.
    cleaned_records = []
    for record in records:
        new_record = {
            'game_type': record.get('game_type'),
            'countryCode': record.get('countryCode'),
            'total_score': int(record.get('total_score', 0)),
            'country_name': record.get('country_name'),
            'rank': int(record.get('rank', 0))
        }
        contributors_list = []
        # Safely handle the top_contributors - it can be a numpy array or list
        top_contributors = record.get('top_contributors')
        if top_contributors is not None:
            # Convert numpy array to list if needed
            if hasattr(top_contributors, 'tolist'):
                top_contributors = top_contributors.tolist()
            elif isinstance(top_contributors, np.ndarray):
                top_contributors = top_contributors.tolist()
            
            # Process the contributors
            if isinstance(top_contributors, list):
                for contributor in top_contributors:
                    if isinstance(contributor, dict):
                        contributors_list.append({
                            'name': contributor.get('name'),
                            'score': int(contributor.get('score', 0))
                        })
        new_record['top_contributors'] = contributors_list
        cleaned_records.append(new_record)

    return jsonify(cleaned_records)


@app.route('/api/search-player/<game_type>/<player_name>')
def search_player_contributions(game_type, player_name):
    """Search for a player's contributions across all nations for a specific game type."""
    if player_contributions_df is None:
        return jsonify({"error": "Player contributions data not available. Please run 'nation_ranking_pipeline.py' again to generate it."}), 500

    game_type_str = game_type.replace('%20', ' ')
    player_name_lower = player_name.lower()
    
    # Filter by game type first
    game_data = player_contributions_df[player_contributions_df['game_type'] == game_type_str]
    
    # Search for players whose names contain the search term
    matching_players = game_data[
        game_data['name'].str.lower().str.contains(player_name_lower, na=False)
    ]
    
    if matching_players.empty:
        return jsonify([])
    
    # Group by player name and aggregate their contributions
    results = []
    for player_name_exact in matching_players['name'].unique():
        player_data = matching_players[matching_players['name'] == player_name_exact]
        
        contributions = []
        total_score = 0
        
        for _, row in player_data.iterrows():
            contribution = {
                'country_name': row.get('country_name', row.get('countryCode', 'Unknown')),
                'countryCode': row.get('countryCode', ''),
                'score': int(row.get('score', 0))
            }
            contributions.append(contribution)
            total_score += contribution['score']
        
        # Sort contributions by score (highest first)
        contributions.sort(key=lambda x: x['score'], reverse=True)
        
        results.append({
            'player_name': player_name_exact,
            'total_score': total_score,
            'contributions': contributions,
            'game_type': game_type_str
        })
    
    # Sort results by total score (highest first)
    results.sort(key=lambda x: x['total_score'], reverse=True)
    
    return jsonify(results)


@app.route('/api/nation-score-breakdown/<country_code>/<game_type>')
def get_nation_score_breakdown(country_code, game_type):
    """Provides detailed breakdown of how a nation's score is calculated."""
    if player_contributions_df is None or nation_rankings_df is None:
        return jsonify({"error": "Data not available."}), 500

    country_code = country_code.upper()
    game_type_str = game_type.replace('%20', ' ')
    
    # Get nation ranking info for k value and other stats
    nation_info = nation_rankings_df[
        (nation_rankings_df['countryCode'] == country_code) & 
        (nation_rankings_df['game_type'] == game_type_str)
    ]
    
    if nation_info.empty:
        return jsonify({"error": f"No ranking data found for {country_code} in {game_type_str}"}), 404
    
    nation_row = nation_info.iloc[0]
    
    # Get all players for this country and game type
    country_players = player_contributions_df[
        (player_contributions_df['countryCode'] == country_code) & 
        (player_contributions_df['game_type'] == game_type_str)
    ].copy()

    if country_players.empty:
        return jsonify({"error": f"No player data found for {country_code} in {game_type_str}"}), 404

    # Calculate statistics
    total_players = len(country_players)
    raw_score = int(country_players['score'].sum())
    total_games = int(nation_row.get('total_games', country_players['score'].abs().sum()))
    
    # Get k value and other scoring info from nation ranking
    k_value = float(nation_row.get('k_value', 0))
    confidence_factor = float(nation_row.get('confidence_factor', k_value * 2))
    adjusted_score = float(nation_row.get('total_score', 0))
    min_games_required = float(nation_row.get('min_games_required', k_value / 4))
    
    # Calculate win/loss breakdown
    wins = len(country_players[country_players['score'] > 0])
    losses = len(country_players[country_players['score'] < 0])
    
    positive_players = len(country_players[country_players['score'] > 0])
    negative_players = len(country_players[country_players['score'] < 0])
    zero_players = len(country_players[country_players['score'] == 0])
    
    positive_score_sum = int(country_players[country_players['score'] > 0]['score'].sum())
    negative_score_sum = int(country_players[country_players['score'] < 0]['score'].sum())
    
    # Get top contributors (positive only)
    top_positive = country_players[country_players['score'] > 0].nlargest(10, 'score')
    
    # Convert to clean records
    top_positive_list = []
    for _, player in top_positive.iterrows():
        top_positive_list.append({
            'name': player['name'],
            'score': int(player['score']),
            'wins': int(player['score']),  # Since wins = +1 each
            'losses': 0  # If score is positive, no net losses
        })

    # Get country name
    country_name = country_players['country_name'].iloc[0] if not country_players.empty else country_code

    # Calculate what the score would be without the confidence factor
    raw_percentage = (raw_score / total_games) * 10000 if total_games > 0 else 0
    
    breakdown = {
        'country_code': country_code,
        'country_name': country_name,
        'game_type': game_type_str,
        'adjusted_score': adjusted_score,
        'raw_score': raw_score,
        'raw_percentage': round(raw_percentage, 2),
        'total_games': total_games,
        'total_players': total_players,
        'handicap_info': {
            'k_value': round(k_value, 1),
            'confidence_factor': round(confidence_factor, 1),
            'min_games_required': round(min_games_required, 1),
            'meets_minimum': total_games >= min_games_required,
            'explanation': f'Confidence Factor of {confidence_factor:.1f} games added to denominator. Minimum {min_games_required:.1f} games required for leaderboard.'
        },
        'player_distribution': {
            'positive_players': positive_players,
            'negative_players': negative_players,
            'zero_players': zero_players
        },
        'score_breakdown': {
            'total_wins': positive_score_sum,
            'total_losses': abs(negative_score_sum),
            'net_score': raw_score,
            'win_rate_percentage': round((positive_score_sum / total_games) * 100, 1) if total_games > 0 else 0
        },
        'explanation': {
            'scoring_system': 'Adjusted Score = (Wins - Losses) / (Total Games + Confidence Factor) × 10000',
            'calculation': f'({positive_score_sum} - {abs(negative_score_sum)}) / ({total_games} + {confidence_factor:.1f}) × 10000 = {adjusted_score:.0f}',
            'interpretation': 'The Confidence Factor is added to the denominator, making it larger. This means nations with fewer games get lower scores (bigger denominator = smaller result), while nations with many games are barely affected. This prevents small samples from dominating the leaderboard.',
            'how_it_works': f'Without Confidence Factor, this nation would score {raw_percentage:.0f}. With the factor of {confidence_factor:.1f} added to the denominator, the score becomes {adjusted_score:.0f}. The more games played, the less impact the factor has.',
            'comparison': f'Without Confidence Factor: {raw_percentage:.0f}, With Confidence Factor: {adjusted_score:.0f}'
        },
        'top_contributors': top_positive_list
    }

    return jsonify(breakdown)


@app.route('/api/status')
def get_status():
    """Provides status information for the leaderboard."""
    return jsonify({
        "status": "online",
        "last_updated": last_updated_time,
        "message": "BAR Leaderboard is operational"
    })

@app.route('/api/leaderboards')
def get_leaderboards():
    """Provides list of available leaderboards."""
    if leaderboard_df is None:
        return jsonify({"error": "Leaderboard data not available"}), 500
    
    # Get unique leaderboard types from the data
    nations = []
    regions = []
    
    for leaderboard_id in leaderboard_df['leaderboard_id'].unique():
        # Use leaderboard_id as name if it's descriptive, otherwise use country mapping
        if len(leaderboard_id) > 2:  # Likely a region name
            country_name = leaderboard_id
            regions.append({
                "id": leaderboard_id,
                "name": country_name,
                "code": leaderboard_id
            })
        else:
            country_name = country_name_map.get(leaderboard_id, leaderboard_id)
            nations.append({
                "id": leaderboard_id,
                "name": country_name,
                "code": leaderboard_id
            })
    
    # Sort by country name
    nations.sort(key=lambda x: x['name'])
    regions.sort(key=lambda x: x['name'])
    
    return jsonify({
        "nations": nations,
        "regions": regions
    })

@app.route('/api/leaderboard/<leaderboard_id>/<game_type>')
def get_leaderboard(leaderboard_id, game_type):
    """Get leaderboard data for a specific leaderboard and game type."""
    if processed_leaderboards_cache is None:
        return jsonify({"error": "Leaderboard data not available"}), 500
    
    game_type_str = game_type.replace('%20', ' ')
    cache_key = f"{leaderboard_id}_{game_type_str}"
    
    # Use preprocessed data for fast lookup
    if cache_key in processed_leaderboards_cache:
        return jsonify(processed_leaderboards_cache[cache_key])
    else:
        return jsonify({"players": [], "total_players": 0})

@app.route('/api/leaderboard/global/<game_type>')
def get_global_leaderboard(game_type):
    """Get global leaderboard data for a specific game type."""
    if processed_leaderboards_cache is None:
        return jsonify({"error": "Leaderboard data not available"}), 500
    
    game_type_str = game_type.replace('%20', ' ')
    cache_key = f"global_{game_type_str}"
    
    # Use preprocessed data for fast lookup
    if cache_key in processed_leaderboards_cache:
        return jsonify(processed_leaderboards_cache[cache_key])
    else:
        return jsonify({"players": [], "total_players": 0})


@app.route('/api/efficiency-data')
def get_efficiency_data():
    """Provides efficiency vs speed analysis data for plotting."""
    efficiency_file = os.path.join(BASE_DIR, 'data', 'efficiency_vs_speed_analysis_with_names.csv')
    
    if not os.path.exists(efficiency_file):
        return jsonify({"error": "Efficiency analysis data not available"}), 500
    
    try:
        df = pd.read_csv(efficiency_file)
        
        # Convert to more intuitive units
        df['metal_efficiency_per_100'] = df['metal_efficiency'] * 100  # Energy per 100 metal
        df['time_efficiency_per_1000'] = df['time_efficiency'] * 1000  # Energy per 1000 build time
        
        # Include all energy buildings (both variable and fixed)
        # Group by faction for separate datasets
        arm_data = df[df['faction'] == 'ARM']
        cor_data = df[df['faction'] == 'COR']
        
        return jsonify({
            'arm_data': arm_data.to_dict('records'),
            'cor_data': cor_data.to_dict('records')
        })
        
    except Exception as e:
        return jsonify({"error": f"Error loading efficiency data: {str(e)}"}), 500

@app.route('/api/team-rankings')
def get_team_rankings():
    """Get team rankings data."""
    try:
        if not os.path.exists(TEAM_ANALYSIS_FILE):
            return jsonify({"error": "Team analysis data not available. Please run team analysis first."}), 404
        
        with open(TEAM_ANALYSIS_FILE, 'r') as f:
            roster_data = json.load(f)
        
        # Transform the roster data to the expected frontend format
        team_data = {
            "analysis_date": roster_data.get("analysis_date"),
            "config": roster_data.get("config"),
            "summary": roster_data.get("summary"),
            "party_teams": roster_data.get("rosters", []),
            "frequent_pairs": []  # Empty since we're only doing party-based analysis
        }
        
        return jsonify(team_data)
    except Exception as e:
        return jsonify({"error": f"Error loading team data: {str(e)}"}), 500

@app.route('/api/team-rankings/<team_type>')
def get_team_rankings_by_type(team_type):
    """Get team rankings data by type (party_teams, frequent_teammates)."""
    try:
        if not os.path.exists(TEAM_ANALYSIS_FILE):
            return jsonify({"error": "Team analysis data not available. Please run team analysis first."}), 404
        
        with open(TEAM_ANALYSIS_FILE, 'r') as f:
            roster_data = json.load(f)
        
        # Transform the roster data to the expected frontend format
        if team_type == 'party_teams':
            return jsonify({team_type: roster_data.get("rosters", [])})
        elif team_type == 'frequent_teammates' or team_type == 'frequent_pairs':
            return jsonify({team_type: []})  # Empty since we're only doing party-based analysis
        else:
            return jsonify({"error": f"Team type '{team_type}' not found"}), 404
        
    except Exception as e:
        return jsonify({"error": f"Error loading team data: {str(e)}"}), 500

@app.route('/api/player-suggestions/<partial_name>')
def get_player_suggestions(partial_name):
    """Get player name suggestions for autocomplete."""
    try:
        if not os.path.exists(TEAM_ANALYSIS_FILE):
            return jsonify({"error": "Team analysis data not available."}), 404
        
        with open(TEAM_ANALYSIS_FILE, 'r') as f:
            roster_data = json.load(f)
        
        partial_name_lower = partial_name.lower()
        suggestions = set()
        
        # Collect all unique player names from roster data (party teams)
        for team in roster_data.get('rosters', []):
            for player in team.get('roster', []):
                name = player.get('name', '')
                if name and partial_name_lower in name.lower():
                    suggestions.add(name)
        
        # Also collect from communities data
        for community in roster_data.get('communities', []):
            for player in community.get('roster', []):
                name = player.get('name', '')
                if name and partial_name_lower in name.lower():
                    suggestions.add(name)
        
        # Return sorted suggestions, limited to 10
        sorted_suggestions = sorted(list(suggestions))[:10]
        
        return jsonify({
            'suggestions': sorted_suggestions,
            'query': partial_name
        })
        
    except Exception as e:
        return jsonify({"error": f"Error getting suggestions: {str(e)}"}), 500

@app.route('/api/search-teams/<player_name>')
@app.route('/api/search-teams/<player_name>/<search_type>')
def search_teams_by_player(player_name, search_type='party_teams'):
    """Search for teams that contain a specific player."""
    try:
        if not os.path.exists(TEAM_ANALYSIS_FILE):
            return jsonify({"error": "Team analysis data not available. Please run team analysis first."}), 404
        
        with open(TEAM_ANALYSIS_FILE, 'r') as f:
            roster_data = json.load(f)
        
        player_name_lower = player_name.lower()
        player_items = []
        
        # Search through party teams (only supported search type)
        for team in roster_data.get('rosters', []):
            for player in team.get('roster', []):
                if player_name_lower in player['name'].lower():
                    # Add player_details field for frontend compatibility
                    team_copy = team.copy()
                    team_copy['player_details'] = team_copy.get('roster', [])
                    player_items.append({
                        **team_copy,
                        'team_type': 'party',
                        'search_match': player
                    })
                    break
        
        # Sort teams by relevance (exact matches first, then by team activity)
        def sort_key(item):
            exact_match = player_name_lower == item['search_match']['name'].lower()
            activity = item.get('stats_overall', {}).get('matches', 0)
            return (-int(exact_match), -activity)
        
        player_items.sort(key=sort_key)
        
        return jsonify({
            'player_name': player_name,
            'search_type': search_type,
            'items_found': len(player_items),
            'teams': player_items[:20]  # Limit to top 20 results
        })
        
    except Exception as e:
        return jsonify({"error": f"Error searching for player teams: {str(e)}"}), 500



if __name__ == '__main__':
    app.run(debug=True)

