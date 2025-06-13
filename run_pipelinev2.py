import os
import json
import csv
import time
import requests
import pandas as pd
import ssl
from io import BytesIO

# ==============================================================================
# --- Master Configuration ---
# ==============================================================================
DATA_FOLDER = "data"
REPLAYS_FOLDER = os.path.join(DATA_FOLDER, "replays")
PROCESSED_IDS_FILE = os.path.join(DATA_FOLDER, "processed_ids.txt")
REPLAYS_LIST_URL = "https://api.bar-rts.com/replays"
BASE_REPLAY_URL = "https://api.bar-rts.com/replays/"
TIME_BETWEEN_REQUESTS = 0.5
EXTRACTED_PLAYERS_CSV = os.path.join(DATA_FOLDER, "players_data.csv")
PLAYERS_PARQUET_URL = 'https://data-marts.beyondallreason.dev/players.parquet'
MERGED_PLAYERS_FILE = os.path.join(DATA_FOLDER, "players_with_countries.parquet")
MATCHES_URL = 'https://data-marts.beyondallreason.dev/matches.parquet'
MATCH_PLAYERS_URL = 'https://data-marts.beyondallreason.dev/match_players.parquet'
FINAL_LEADERBOARD_FILE = os.path.join(DATA_FOLDER, "final_leaderboard.parquet")
ISO_COUNTRIES_FILE = os.path.join(DATA_FOLDER, "iso_country.csv")

# --- Proxy and SSL Configuration ---
# PROXIES = { "http": "http://proxy.server:3128", "https": "http://proxy.server:3128" } # Enable for PythonAnywhere free accounts
PROXIES = None # Use for local execution
ssl._create_default_https_context = ssl._create_unverified_context
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}

# ==============================================================================
# --- Helper Functions ---
# ==============================================================================
def make_request(url: str):
    """Makes a GET request with specified headers and proxies."""
    return requests.get(url, headers=HEADERS, proxies=PROXIES)

def download_parquet_to_dataframe(url: str) -> pd.DataFrame:
    """Downloads a Parquet file from a URL and loads it into a pandas DataFrame."""
    print(f"  -> Downloading data from: {url}")
    response = make_request(url)
    response.raise_for_status()
    return pd.read_parquet(BytesIO(response.content))

# ==============================================================================
# --- Pipeline Step 1: Replay Downloader (Modified) ---
# ==============================================================================
def step_1_download_replays():
    """
    Downloads new replays from the API.
    This function now stops searching as soon as it encounters a replay ID
    that has already been processed and saved in processed_ids.txt.
    It will check pages continuously until a known replay or the end of the list is found.
    """
    print("\n--- [Step 1/4] Starting Replay Download ---")
    if not os.path.exists(REPLAYS_FOLDER):
        os.makedirs(REPLAYS_FOLDER)

    # Load the set of already processed replay IDs
    processed_ids = set()
    if os.path.exists(PROCESSED_IDS_FILE):
        with open(PROCESSED_IDS_FILE, 'r', encoding='utf-8') as f:
            processed_ids = {line.strip() for line in f}
    
    ids_to_download = []
    # Flag to signal that we should stop all searching because a known replay was found.
    stop_searching = False

    print("-> Checking for new replays until a known replay is found or all pages are checked.")
    page_num = 1
    while True: # Loop indefinitely through pages until a break condition is met.
        try:
            print(f"-> Checking Page: {page_num}...", end='\r')
            response = make_request(f"{REPLAYS_LIST_URL}?page={page_num}")
            response.raise_for_status()
            replays_on_page = response.json().get('data', [])
            
            # Stop if the API returns an empty page, meaning we've reached the end.
            if not replays_on_page:
                print("\n-> Reached the last page of available replays.")
                break

            for replay in replays_on_page:
                replay_id = replay.get('id')
                if replay_id:
                    if replay_id not in processed_ids:
                        # This is a new replay, add it to the download list
                        ids_to_download.append(replay_id)
                    else:
                        # This replay has been seen before. Halt the search.
                        print(f"\n-> Found already analyzed replay ID: {replay_id}. Halting search for new replays.")
                        stop_searching = True
                        break # Exit the inner loop (for replays on the current page)
        
        except Exception as e:
            print(f"\nAn error occurred while fetching the replay list: {e}")
            break # Stop searching on error
        
        # If the flag was set, break out of the outer loop (for pages) as well.
        if stop_searching:
            break
        
        page_num += 1 # Prepare for the next page
        time.sleep(TIME_BETWEEN_REQUESTS)
    
    print() # Newline after the progress indicator
    if not ids_to_download:
        print("-> No new replays found to download.")
    else:
        print(f"-> Found {len(ids_to_download)} new replays. Starting download...")
        for replay_id in ids_to_download:
            try:
                # Download the full replay JSON
                replay_response = make_request(f"{BASE_REPLAY_URL}{replay_id}")
                replay_response.raise_for_status()
                
                # Save the replay JSON to a file
                with open(os.path.join(REPLAYS_FOLDER, f"{replay_id}.json"), 'w', encoding='utf-8') as f:
                    json.dump(replay_response.json(), f)
                
                # Add the ID to our processed list to avoid re-downloading
                with open(PROCESSED_IDS_FILE, 'a', encoding='utf-8') as f:
                    f.write(f"{replay_id}\n")
            except Exception as e:
                print(f"  -> Error downloading replay {replay_id}: {e}")
            time.sleep(TIME_BETWEEN_REQUESTS)
            
    print("--- [Step 1/4] Replay Download Complete ---")

# ==============================================================================
# --- Pipeline Step 2: JSON Processor ---
# ==============================================================================
def step_2_extract_player_data():
    """Extracts player information from downloaded JSON replays."""
    print("\n--- [Step 2/4] Starting Player Data Extraction ---")
    existing_players = {}
    
    # Load existing player data to avoid duplicates and preserve country codes
    if os.path.exists(EXTRACTED_PLAYERS_CSV):
        try:
            df = pd.read_csv(EXTRACTED_PLAYERS_CSV)
            existing_players = {row['userId']: {'name': row['name'], 'countryCode': row.get('countryCode')} for index, row in df.iterrows()}
        except pd.errors.EmptyDataError:
            pass # File is empty, we will start fresh

    replay_files = [f for f in os.listdir(REPLAYS_FOLDER) if f.endswith('.json')]
    if not replay_files:
        print("-> No JSON files to process in the 'replays' folder.")
        return

    print(f"-> Found {len(replay_files)} JSON files to process.")
    new_players_found = 0
    for filename in replay_files:
        filepath = os.path.join(REPLAYS_FOLDER, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                replay_data = json.load(f)

            def process_person_list(person_list):
                nonlocal new_players_found
                for person in person_list:
                    user_id = person.get('userId')
                    # If the player is not already in our list, add them.
                    if user_id and user_id not in existing_players:
                        existing_players[user_id] = {'name': person.get('name'), 'countryCode': person.get('countryCode')}
                        new_players_found += 1
            
            # Process players from all teams
            for team in replay_data.get('AllyTeams', []):
                process_person_list(team.get('Players', []))
            # Process spectators as well
            process_person_list(replay_data.get('Spectators', []))
            
            # The line to remove the JSON file has been commented out to keep the replays.
            # os.remove(filepath) 
            
        except Exception as e:
            print(f"  -> Error processing {filename}: {e}")
            
    if new_players_found > 0:
        # Save the updated player list to CSV
        output_data = [{'userId': uid, **data} for uid, data in existing_players.items()]
        pd.DataFrame(output_data).to_csv(EXTRACTED_PLAYERS_CSV, index=False)
        print(f"-> Player data updated with {new_players_found} new entries in {EXTRACTED_PLAYERS_CSV}.")
    else:
        print("-> No new players found in the JSON replays.")
    print("--- [Step 2/4] Player Data Extraction Complete ---")

# ==============================================================================
# --- Pipeline Step 3: Player Data Merger ---
# ==============================================================================
def step_3_merge_player_data():
    """Merges the main player list with the extracted country codes."""
    print("\n--- [Step 3/4] Starting Player/Country Merge ---")
    if not os.path.exists(EXTRACTED_PLAYERS_CSV):
        print(f"-> Error: Player data file '{EXTRACTED_PLAYERS_CSV}' not found. Please run Step 2 first. Skipping.")
        return
    try:
        # Download the main player list from the data mart
        players_df = download_parquet_to_dataframe(PLAYERS_PARQUET_URL)
        # Load our locally extracted player data with country codes
        nationalities_df = pd.read_csv(EXTRACTED_PLAYERS_CSV)
        
        # Merge the two dataframes
        merged_df = pd.merge(players_df[['user_id', 'name']], nationalities_df, left_on='user_id', right_on='userId', how='left')
        
        # Clean up columns from the merge
        merged_df = merged_df.drop(columns=['userId', 'name_y']).rename(columns={'name_x': 'name'})
        
        # Save the result to a Parquet file
        merged_df.to_parquet(MERGED_PLAYERS_FILE, index=False)
        print(f"-> Successfully merged and saved {len(merged_df)} records to {MERGED_PLAYERS_FILE}.")
    except Exception as e:
        print(f"-> An error occurred during the merge: {e}")
    print("--- [Step 3/4] Player/Country Merge Complete ---")

# ==============================================================================
# --- Pipeline Step 4: Final Leaderboard Calculation ---
# ==============================================================================
def step_4_calculate_leaderboard():
    """Calculates national, regional, and custom leaderboards."""
    print("\n--- [Step 4/4] Starting Final Leaderboard Calculation ---")
    try:
        # Load all necessary dataframes
        matches_df = download_parquet_to_dataframe(MATCHES_URL)
        match_players_df = download_parquet_to_dataframe(MATCH_PLAYERS_URL)
        players_countries_df = pd.read_parquet(MERGED_PLAYERS_FILE)
        iso_df = pd.read_csv(ISO_COUNTRIES_FILE)

        # Filter for ranked matches in specific game types
        game_types = ["Large Team", "Small Team", "Duel"]
        filtered_matches = matches_df[(matches_df['is_ranked'] == True) & (matches_df['game_type'].isin(game_types))]
        
        # Combine match data with player data
        game_stats_df = pd.merge(filtered_matches, match_players_df, on='match_id', how='inner')
        full_data_df = pd.merge(game_stats_df, players_countries_df, on='user_id', how='inner')
        
        # Clean data: remove entries with no country code or '??'
        full_data_df.dropna(subset=['countryCode'], inplace=True)
        full_data_df = full_data_df[full_data_df['countryCode'] != '??'].copy()

        # Add region information using the ISO country data
        iso_subset_df = iso_df[['alpha-2', 'sub-region']].rename(columns={'alpha-2': 'countryCode'})
        full_data_df = pd.merge(full_data_df, iso_subset_df, on='countryCode', how='left')
        
        # Consolidate Oceania sub-regions into a single 'Oceania' region
        oceania_regions = ['Melanesia', 'Micronesia', 'Polynesia']
        full_data_df['sub-region'].replace(oceania_regions, 'Oceania', inplace=True)
        full_data_df['sub-region'].fillna('Other', inplace=True)

        # 1. National Leaderboards (countries with at least 15 players)
        player_counts = full_data_df.groupby(['game_type', 'countryCode'])['user_id'].transform('nunique')
        national_df = full_data_df[player_counts >= 15].copy()
        national_df['leaderboard_id'] = national_df['countryCode']
        
        # 2. Regional Leaderboards
        regional_df = full_data_df.copy()
        regional_df['leaderboard_id'] = regional_df['sub-region']
        
        # 3. Custom Leaderboard: Benelux
        benelux_codes = ['BE', 'NL', 'LU']
        benelux_df = full_data_df[full_data_df['countryCode'].isin(benelux_codes)].copy()
        benelux_df['leaderboard_id'] = 'Benelux'

        # Combine all leaderboards into a single dataframe
        combined_df = pd.concat([national_df, regional_df, benelux_df], ignore_index=True)
        
        # Calculate the rating and get the most recent entry for each player-leaderboard combination
        combined_df['leaderboard_rating'] = combined_df['new_skill'] - combined_df['new_uncertainty']
        combined_df.sort_values(by='start_time', ascending=False, inplace=True)
        final_df = combined_df.drop_duplicates(subset=['user_id', 'game_type', 'leaderboard_id'], keep='first')
        
        # Select and order the final columns
        final_cols = ['user_id', 'name', 'countryCode', 'leaderboard_id', 'game_type', 'leaderboard_rating', 'new_skill', 'new_uncertainty', 'start_time', 'match_id']
        final_df = final_df[final_cols].copy()
        
        # Save the final leaderboard
        final_df.to_parquet(FINAL_LEADERBOARD_FILE, index=False)
        print(f"-> Calculated and saved final leaderboard with {len(final_df)} unique entries to {FINAL_LEADERBOARD_FILE}.")
    except Exception as e:
        print(f"-> An error occurred during the final calculation: {e}")
    print("--- [Step 4/4] Final Leaderboard Calculation Complete ---")


# ==============================================================================
# --- Main Execution Block ---
# ==============================================================================
if __name__ == '__main__':
    print("===== Starting Data Pipeline =====")
    step_1_download_replays()
    step_2_extract_player_data()
    step_3_merge_player_data()
    step_4_calculate_leaderboard()
    print("\n===== Pipeline Finished Successfully! =====")
