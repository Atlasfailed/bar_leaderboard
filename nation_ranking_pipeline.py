import os
import pandas as pd
from datetime import datetime, timedelta
import requests
from io import BytesIO
import ssl
import traceback
import time

# ==============================================================================
# --- Master Configuration ---
# ==============================================================================
DATA_FOLDER = "data"
# These URLs point to pre-compiled data marts, NOT individual replays.
MATCHES_URL = 'https://data-marts.beyondallreason.dev/matches.parquet'
MATCH_PLAYERS_URL = 'https://data-marts.beyondallreason.dev/match_players.parquet'
CACHE_DURATION_HOURS = 24

# This file is created by the run_pipelinev2.py script.
# NOTE: The run_pipelinev2.py script IS responsible for downloading replays
# to get player country codes. This nation_ranking_pipeline script relies on its output.
PLAYERS_WITH_COUNTRIES_FILE = os.path.join(DATA_FOLDER, "players_with_countries.parquet")
NATION_RANKINGS_FILE = os.path.join(DATA_FOLDER, "nation_rankings.parquet")
# --- NEW FILE FOR SEARCH FUNCTIONALITY ---
PLAYER_CONTRIBUTIONS_FILE = os.path.join(DATA_FOLDER, "player_contributions.parquet")
ISO_COUNTRIES_FILE = os.path.join(DATA_FOLDER, "iso_country.csv")

# --- Proxy and SSL Configuration ---
PROXIES = None 
ssl._create_default_https_context = ssl._create_unverified_context
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}

# ==============================================================================
# --- Helper Functions ---
# ==============================================================================
def make_request(url: str):
    """Makes a GET request with specified headers and proxies."""
    return requests.get(url, headers=HEADERS, proxies=PROXIES)

def get_data_mart(url: str, local_filename: str, base_dir: str) -> pd.DataFrame:
    """
    Downloads a data mart if it's missing or older than CACHE_DURATION_HOURS.
    Otherwise, loads it from the local cache.
    """
    local_filepath = os.path.join(base_dir, DATA_FOLDER, local_filename)
    
    if os.path.exists(local_filepath):
        file_mod_time = os.path.getmtime(local_filepath)
        if (time.time() - file_mod_time) / 3600 < CACHE_DURATION_HOURS:
            print(f"  -> Loading '{local_filename}' from local cache (less than {CACHE_DURATION_HOURS} hours old).")
            df = pd.read_parquet(local_filepath)
            print(f"     ...Loaded {len(df)} rows.")
            return df

    print(f"  -> Downloading fresh data mart from: {url}")
    try:
        response = make_request(url)
        response.raise_for_status()
        df = pd.read_parquet(BytesIO(response.content))
        df.to_parquet(local_filepath, index=False)
        print(f"     ...Downloaded and cached {len(df)} rows to '{local_filepath}'.")
        return df
    except Exception as e:
        print(f"  -> ERROR: Failed to download {url}: {e}")
        if os.path.exists(local_filepath):
            print(f"  -> FALLBACK: Using stale cache file '{local_filepath}' due to download error.")
            return pd.read_parquet(local_filepath)
        else:
            raise

# ==============================================================================
# --- Main Calculation Function ---
# ==============================================================================
def calculate_nation_rankings():
    """
    Calculates nation rankings and saves a complete list of all player contributions.
    """
    print("\n--- Starting Nation Ranking Calculation (with full player contributions) ---")
    try:
        # Get the directory of this script to build the correct path to the data folder
        base_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Define paths relative to the script's location
        data_path = os.path.join(base_dir, 'data')
        players_with_countries_path = os.path.join(data_path, "players_with_countries.parquet")
        nation_rankings_path = os.path.join(data_path, "nation_rankings.parquet")
        player_contributions_path = os.path.join(data_path, "player_contributions.parquet")
        iso_countries_path = os.path.join(data_path, "iso_country.csv")


        # 1. Load Data
        print("\n-> Step 1/7: Loading core data...")
        matches_df = get_data_mart(MATCHES_URL, "matches.parquet", base_dir)
        match_players_df = get_data_mart(MATCH_PLAYERS_URL, "match_players.parquet", base_dir)

        if not os.path.exists(players_with_countries_path):
             print(f"\nFATAL ERROR: Player country data file not found at '{players_with_countries_path}'. Run 'run_pipelinev2.py' first.")
             return
        
        players_countries_df = pd.read_parquet(players_with_countries_path)
        iso_df = pd.read_csv(iso_countries_path)
        country_name_map = pd.Series(iso_df.name.values, index=iso_df['alpha-2'].str.strip()).to_dict()
        valid_country_codes = set(iso_df['alpha-2'].str.strip())

        # 2. Filter Data
        print("\n-> Step 2/7: Filtering for recent, ranked matches...")
        seven_days_ago = pd.to_datetime(datetime.utcnow().date()) - timedelta(days=7)
        matches_df['start_time'] = pd.to_datetime(matches_df['start_time'])
        recent_matches_df = matches_df[matches_df['start_time'] >= seven_days_ago].copy()
        game_types = ["Large Team", "Small Team", "Duel"]
        filtered_matches_df = recent_matches_df[(recent_matches_df['is_ranked'] == True) & (recent_matches_df['game_type'].isin(game_types))]
        print(f"  -> Found {len(filtered_matches_df)} relevant matches.")

        # 3. Merge and Validate
        print("\n-> Step 3/7: Merging data sources and validating...")
        match_stats_df = pd.merge(filtered_matches_df, match_players_df, on='match_id', how='inner')
        full_data_df = pd.merge(match_stats_df, players_countries_df[['user_id', 'countryCode']], on='user_id', how='inner')
        full_data_df.dropna(subset=['countryCode'], inplace=True)
        full_data_df = full_data_df[full_data_df['countryCode'].isin(valid_country_codes)]
        print(f"  -> {len(full_data_df)} valid player entries remaining for calculation.")
        if full_data_df.empty:
            print("  -> No valid data to process. Exiting.")
            return

        # 4. Calculate Scores
        print("\n-> Step 4/7: Calculating win/loss scores...")
        full_data_df['is_win'] = (full_data_df['team_id'] == full_data_df['winning_team']).astype(int)
        full_data_df['score'] = full_data_df['is_win'].apply(lambda x: 1 if x == 1 else -1)

        # 5. Aggregate Nation Scores with Dynamic Handicap Adjustment
        print("\n-> Step 5/7: Aggregating scores by nation with dynamic handicap adjustment...")
        
        # First get raw scores and total games per nation
        nation_stats = full_data_df.groupby(['game_type', 'countryCode']).agg({
            'score': 'sum',
            'user_id': 'count'  # Total games played by this nation
        }).reset_index()
        nation_stats.rename(columns={'score': 'raw_score', 'user_id': 'total_games'}, inplace=True)
        
        # Calculate dynamic k value for each game type
        print("  -> Calculating dynamic confidence factor values (k) for each game type...")
        k_values = {}
        for game_type in nation_stats['game_type'].unique():
            game_data = nation_stats[nation_stats['game_type'] == game_type]
            total_games_all_nations = game_data['total_games'].sum()
            total_nations = len(game_data)
            average_games_per_nation = total_games_all_nations / total_nations
            k_value = average_games_per_nation / 2
            k_values[game_type] = k_value
            print(f"    -> {game_type}: Average games per nation = {average_games_per_nation:.1f}, k = {k_value:.1f}")
        
        # Apply the adjusted scoring formula: (Wins - Losses) / (Total Games + 2k) * 10000 (whole numbers)
        def calculate_adjusted_score(row):
            game_type = row['game_type']
            raw_score = row['raw_score']
            total_games = row['total_games']
            k = k_values[game_type]
            confidence_factor = 2 * k
            adjusted_score = (raw_score / (total_games + confidence_factor)) * 10000
            return round(adjusted_score, 0)  # Round to whole number
        
        nation_stats['adjusted_score'] = nation_stats.apply(calculate_adjusted_score, axis=1)
        nation_stats['k_value'] = nation_stats['game_type'].map(k_values)
        nation_stats['confidence_factor'] = nation_stats['k_value'] * 2
        
        # Use adjusted score as the total score
        nation_stats['total_score'] = nation_stats['adjusted_score']
        
        # Apply minimum games filter: k / 4 (proportional to activity level)
        print("  -> Applying minimum games filter to remove 'one-hit wonders'...")
        nations_before_filter = len(nation_stats)
        
        def meets_minimum_games(row):
            k_value = row['k_value']
            min_games = k_value / 4  # Minimum games = k / 4
            return row['total_games'] >= min_games
        
        nation_stats['meets_minimum'] = nation_stats.apply(meets_minimum_games, axis=1)
        nation_stats['min_games_required'] = nation_stats['k_value'] / 4
        
        # Show filtering stats per game type
        for game_type in nation_stats['game_type'].unique():
            game_data = nation_stats[nation_stats['game_type'] == game_type]
            before_count = len(game_data)
            after_count = len(game_data[game_data['meets_minimum']])
            min_games = game_data['min_games_required'].iloc[0]
            print(f"    -> {game_type}: {before_count} → {after_count} nations (min {min_games:.1f} games)")
        
        # Filter out nations that don't meet minimum games
        nation_stats_filtered = nation_stats[nation_stats['meets_minimum']].copy()
        nations_after_filter = len(nation_stats_filtered)
        print(f"  -> Filtered from {nations_before_filter} to {nations_after_filter} nations total")
        
        # Keep all the stats for the breakdown API (including min games info)
        nation_scores_df = nation_stats_filtered[['game_type', 'countryCode', 'total_score', 'raw_score', 'total_games', 'k_value', 'confidence_factor', 'min_games_required']].copy()
        
        print(f"  -> Applied confidence factor adjustment and filtering. Sample scores for verification:")
        sample_nations = nation_scores_df.groupby('game_type').head(3)
        for _, row in sample_nations.iterrows():
            print(f"    -> {row['countryCode']} ({row['game_type']}): {row['raw_score']}/{row['total_games']} games → {row['total_score']:.0f} (k={row['k_value']:.1f}, min={row['min_games_required']:.1f})")

        # 6. Aggregate ALL Player Contributions for Search
        print("\n-> Step 6/7: Aggregating all player contributions...")
        player_scores_df = pd.merge(full_data_df, players_countries_df[['user_id', 'name']], on='user_id', how='left').dropna(subset=['name'])
        player_agg_scores = player_scores_df.groupby(['game_type', 'countryCode', 'user_id', 'name'])['score'].sum().reset_index()
        
        # --- SAVE THE NEW FILE ---
        player_agg_scores['country_name'] = player_agg_scores['countryCode'].map(country_name_map)
        player_agg_scores.to_parquet(player_contributions_path, index=False)
        print(f"  -> Saved {len(player_agg_scores)} player contribution records to '{player_contributions_path}'.")


        # 7. Final Merge for Nation Leaderboard (Top 5)
        print("\n-> Step 7/7: Finalizing nation leaderboard with top contributors...")
        player_agg_scores.sort_values(by=['game_type', 'countryCode', 'score'], ascending=[True, True, False], inplace=True)
        top_contributors = player_agg_scores.groupby(['game_type', 'countryCode']).head(5)
        contributors_agg = top_contributors.groupby(['game_type', 'countryCode']).apply(
            lambda g: g[['name', 'score']].to_dict('records')
        ).reset_index(name='top_contributors')

        final_rankings_df = pd.merge(nation_scores_df, contributors_agg, on=['game_type', 'countryCode'], how='left')
        final_rankings_df['country_name'] = final_rankings_df['countryCode'].map(country_name_map)
        final_rankings_df.sort_values(by=['game_type', 'total_score'], ascending=[True, False], inplace=True)
        final_rankings_df['rank'] = final_rankings_df.groupby('game_type').cumcount() + 1
        final_rankings_df['top_contributors'] = final_rankings_df['top_contributors'].apply(lambda x: x if isinstance(x, list) else [])
        
        final_rankings_df.to_parquet(nation_rankings_path, index=False)
        print(f"\n--- Successfully calculated and saved nation rankings to '{nation_rankings_path}' ---")

    except Exception as e:
        print(f"\n--- An unrecoverable error occurred during the nation ranking calculation: {e} ---")
        traceback.print_exc()

# ==============================================================================
# --- Main Execution Block ---
# ==============================================================================
if __name__ == '__main__':
    # Create data folder if it doesn't exist relative to this script
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_path = os.path.join(base_dir, 'data')
    if not os.path.exists(data_path):
        os.makedirs(data_path)
    calculate_nation_rankings()
