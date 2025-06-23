#!/usr/bin/env python3
"""
Core Roster Analysis Script for Nation Leaderboard
===================================================

This script identifies stable, premade teams ("core rosters") by analyzing
player collaboration patterns. It uses a hybrid network approach:

1.  A relationship graph is built ONLY from players who have explicitly
    queued together in a party. This uses the `party_id` as a "proof of
    connection" for a single match, eliminating noise from random matchmaking.

2.  A community detection algorithm is run on this high-quality graph to
    find dense clusters of players who frequently play together, even if
    not everyone is available for every game. These clusters are the
    "core rosters".

3.  Each roster is analyzed in detail to calculate win rates, player attendance,
    and other stats, now broken down by game mode for greater accuracy.
"""

import pandas as pd
import networkx as nx
from collections import defaultdict, Counter
import json
from itertools import combinations
import os

# --- Configuration ---
# You can tweak these values to adjust the sensitivity of the analysis.
MIN_MATCHES_FOR_CONNECTION = 5  # A pair must party up at least this many times to be connected.
MIN_TEAM_MATCHES = 10           # A team must have played at least this many games together to be included.
MIN_ROSTER_SIZE = 2             # A roster must have at least this many players.
MAX_ROSTER_SIZE = 10             # A roster can have at most this many players.

def load_data():
    """
    Loads and merges the raw match, player, and country data from the 'data/' directory.
    It combines data from three parquet files into a single master DataFrame.
    """
    print("Loading data...")
    data_dir = 'data'
    try:
        match_players = pd.read_parquet(os.path.join(data_dir, 'match_players.parquet'))
        matches = pd.read_parquet(os.path.join(data_dir, 'matches.parquet'))
        players_with_countries = pd.read_parquet(os.path.join(data_dir, 'players_with_countries.parquet'))
    except FileNotFoundError as e:
        print(f"Error: {e}. Make sure the required .parquet files are in the '{data_dir}/' directory.")
        return None, None

    # MODIFICATION: Merge more columns from the matches table to get game mode info.
    data = match_players.merge(
        matches[['match_id', 'winning_team', 'game_type', 'is_ranked']],
        on='match_id',
        how='left'
    )
    # Merge player identity (name, country) into the data
    data = data.merge(
        players_with_countries[['user_id', 'name', 'countryCode']],
        on='user_id',
        how='left'
    )

    # Fill in missing names for better readability in the final output
    data['name'] = data['name'].fillna(data['user_id'].apply(lambda x: f"Player_{x}"))
    players_with_countries['name'] = players_with_countries['name'].fillna(
        players_with_countries['user_id'].apply(lambda x: f"Player_{x}")
    )
    
    print(f"Loaded {len(data):,} player-match records.")
    return data, players_with_countries


def build_roster_network(data):
    """
    Builds a network graph where connections represent players who have explicitly
    played together in a party. This function is optimized for performance.
    """
    print("\n=== Step 1: Building 'Pre-Made Only' Relationship Graph ===")

    # Filter for records where a party_id exists - our proof of a premade group
    # MODIFICATION: Carry 'game_type' and 'is_ranked' through the analysis.
    party_data = data.loc[data['party_id'].notnull(), ['match_id', 'party_id', 'user_id', 'team_id', 'game_type', 'is_ranked']].copy()
    if party_data.empty:
        print("Warning: No party data found in the dataset. Cannot build roster network.")
        return None, None

    # Group by match and party to get a list of players for each party instance.
    print("Grouping players by party instance...")
    grouped_parties = party_data.groupby(['match_id', 'party_id'])
    
    # Store party information in a more accessible format for later analysis
    party_info_list = [{
        'match_id': name[0],
        'players': sorted(group['user_id'].tolist()),
        'team_id': group['team_id'].iloc[0],
        'game_type': group['game_type'].iloc[0],
        'is_ranked': group['is_ranked'].iloc[0]
    } for name, group in grouped_parties]
    print(f"Found {len(party_info_list):,} unique party instances to analyze.")
    
    # Use a Counter to efficiently count how many times each pair of players parties up
    edge_weights = Counter(
        pair
        for party in party_info_list
        if len(party['players']) > 1
        for pair in combinations(party['players'], 2)
    )

    # Create the graph from the collected edge data
    G = nx.Graph()
    print(f"Found {len(edge_weights):,} unique player pairings from party data.")
    print(f"Filtering connections: A pair must have partied up at least {MIN_MATCHES_FOR_CONNECTION} times.")

    for pair, weight in edge_weights.items():
        if weight >= MIN_MATCHES_FOR_CONNECTION:
            G.add_edge(pair[0], pair[1], weight=weight)

    print(f"--> Roster Network built: {G.number_of_nodes():,} players and {G.number_of_edges():,} reliable connections.")
    return G, party_info_list


def calculate_roster_stats(roster_ids, party_info_list, player_to_party_map, match_win_lookup):
    """
    Calculates detailed statistics for a single roster, now broken down by game mode.
    Only counts matches where this roster has the majority representation of players.
    """
    # OPTIMIZATION: Use the inverted index to get a small, relevant subset of parties
    relevant_party_indices = {idx for pid in roster_ids for idx in player_to_party_map.get(pid, [])}
    
    team_match_info = []
    for idx in relevant_party_indices:
        party_info = party_info_list[idx]
        roster_players_in_match = set(roster_ids).intersection(party_info['players'])
        
        # Only count as team match if:
        # 1. At least 2 roster members present
        # 2. This roster has majority representation (>= 50% of players in the match)
        if len(roster_players_in_match) >= 2:
            total_players_in_match = len(party_info['players'])
            roster_representation = len(roster_players_in_match) / total_players_in_match
            
            # Only count if this roster represents at least 40% of the match
            # (allows for some flexibility while preventing double-counting)
            if roster_representation >= 0.4:
                team_match_info.append(party_info)
    
    if not team_match_info:
        return None

    # --- MODIFICATION: Calculate stats per game mode ---
    stats_by_mode = defaultdict(lambda: {'wins': 0, 'losses': 0, 'matches': 0})

    for match in team_match_info:
        mode = match['game_type'] if pd.notna(match['game_type']) else 'Unknown'
        stats_by_mode[mode]['matches'] += 1
        
        winning_team = match_win_lookup.get(match['match_id'], -1)
        if pd.notna(winning_team) and winning_team >= 0:
            if match['team_id'] == winning_team:
                stats_by_mode[mode]['wins'] += 1
            else:
                stats_by_mode[mode]['losses'] += 1
    
    # Calculate win rates for each mode
    for mode, stats in stats_by_mode.items():
        decided = stats['wins'] + stats['losses']
        stats['win_rate'] = stats['wins'] / decided if decided > 0 else 0.0

    # Get the full list of players across all team matches for attendance and lineup stats
    team_match_lineups = [tuple(sorted(info['players'])) for info in team_match_info]

    player_attendance = Counter(pid for lineup in team_match_lineups for pid in lineup if pid in roster_ids)
    lineup_counts = Counter(team_match_lineups)

    return {
        'total_matches_as_team': len(team_match_info),
        'stats_by_mode': dict(stats_by_mode),
        'player_attendance': dict(player_attendance),
        'most_common_lineups': lineup_counts.most_common(5)
    }


def assign_matches_to_teams(rosters, party_info_list, player_to_party_map):
    """
    Assign each match to the most appropriate team to prevent double-counting.
    Returns a dictionary mapping team_id -> list of match indices.
    """
    print("Assigning matches to teams to prevent double-counting...")
    
    team_matches = {i: [] for i in range(len(rosters))}
    processed_matches = set()
    
    # Get all matches involving any roster players
    all_match_indices = set()
    for roster_ids in rosters:
        for pid in roster_ids:
            all_match_indices.update(player_to_party_map.get(pid, []))
    
    # Process each match once
    for match_idx in all_match_indices:
        if match_idx in processed_matches:
            continue
            
        party_info = party_info_list[match_idx]
        match_players = set(party_info['players'])
        
        # Find which teams have players in this match
        team_representations = []
        for team_idx, roster_ids in enumerate(rosters):
            roster_players_in_match = set(roster_ids).intersection(match_players)
            if len(roster_players_in_match) >= 2:  # At least 2 team members
                representation = len(roster_players_in_match) / len(match_players)
                team_representations.append((team_idx, representation, len(roster_players_in_match)))
        
        # Assign match to the team with highest representation
        if team_representations:
            # Sort by representation percentage, then by absolute count
            team_representations.sort(key=lambda x: (x[1], x[2]), reverse=True)
            best_team = team_representations[0][0]
            
            # Only assign if representation is significant (>= 30%)
            if team_representations[0][1] >= 0.3:
                team_matches[best_team].append(match_idx)
                processed_matches.add(match_idx)
    
    total_assigned = sum(len(matches) for matches in team_matches.values())
    print(f"Assigned {total_assigned} matches to teams (no double-counting)")
    
    return team_matches


def calculate_roster_stats_exclusive(roster_ids, assigned_match_indices, party_info_list, match_win_lookup):
    """
    Calculate roster stats using only the matches exclusively assigned to this team.
    """
    if not assigned_match_indices:
        return None
    
    team_match_info = [party_info_list[idx] for idx in assigned_match_indices]
    
    # --- Calculate stats per game mode ---
    stats_by_mode = defaultdict(lambda: {'wins': 0, 'losses': 0, 'matches': 0})

    for match in team_match_info:
        mode = match['game_type'] if pd.notna(match['game_type']) else 'Unknown'
        stats_by_mode[mode]['matches'] += 1
        
        winning_team = match_win_lookup.get(match['match_id'], -1)
        if pd.notna(winning_team) and winning_team >= 0:
            if match['team_id'] == winning_team:
                stats_by_mode[mode]['wins'] += 1
            else:
                stats_by_mode[mode]['losses'] += 1
    
    # Calculate win rates for each mode
    for mode, stats in stats_by_mode.items():
        decided = stats['wins'] + stats['losses']
        stats['win_rate'] = stats['wins'] / decided if decided > 0 else 0.0

    # Get the full list of players across all team matches for attendance and lineup stats
    team_match_lineups = [tuple(sorted(info['players'])) for info in team_match_info]

    player_attendance = Counter(pid for lineup in team_match_lineups for pid in lineup if pid in roster_ids)
    lineup_counts = Counter(team_match_lineups)

    return {
        'total_matches_as_team': len(team_match_info),
        'stats_by_mode': dict(stats_by_mode),
        'player_attendance': dict(player_attendance),
        'most_common_lineups': lineup_counts.most_common(5)
    }


def detect_and_analyze_rosters(G, party_info_list, players_data, data):
    """
    Detects communities (rosters) and orchestrates the detailed analysis for each one.
    Returns: (analyzed_rosters, unrestricted_communities)
    """
    print("\n=== Step 2: Detecting and Analyzing Core Rosters ===")
    if G is None or G.number_of_nodes() == 0:
        print("Graph is empty. Skipping roster detection.")
        return []

    # --- Pre-computation for performance ---
    print("Creating inverted index and lookups for fast analysis...")
    player_to_party_map = defaultdict(list)
    for i, party_info in enumerate(party_info_list):
        for player_id in party_info['players']:
            player_to_party_map[player_id].append(i)

    match_win_lookup = data.drop_duplicates('match_id').set_index('match_id')['winning_team'].to_dict()
    player_lookup = players_data.set_index('user_id').to_dict('index')

    # --- Community Detection ---
    print("Running community detection algorithm...")
    # Get overlapping communities for teams (strict, party-based only)
    overlapping_communities = detect_overlapping_communities(G)
    
    print(f"Found {len(overlapping_communities)} overlapping communities for teams")
    
    # Use overlapping communities for the main roster analysis
    rosters = []
    for community in overlapping_communities:
        if MIN_ROSTER_SIZE <= len(community) <= MAX_ROSTER_SIZE:
            rosters.append(community)
    
    print(f"Final count: {len(rosters)} potential core rosters to analyze from overlapping detection.")

    # NEW: Assign matches exclusively to teams to prevent double-counting
    team_assigned_matches = assign_matches_to_teams(rosters, party_info_list, player_to_party_map)

    analyzed_rosters = []
    for i, roster_ids in enumerate(rosters):
        # Use exclusive match assignment instead of overlapping assignment
        assigned_matches = team_assigned_matches.get(i, [])
        stats = calculate_roster_stats_exclusive(roster_ids, assigned_matches, party_info_list, match_win_lookup)
        
        # MODIFICATION: Add the filter for minimum team matches.
        if not stats or stats['total_matches_as_team'] < MIN_TEAM_MATCHES:
            continue

        # --- Assemble Roster Details ---
        total_team_matches = stats['total_matches_as_team']
        roster_details = []
        for pid in roster_ids:
            player_info = player_lookup.get(pid, {})
            matches_played = stats['player_attendance'].get(pid, 0)
            roster_details.append({
                'user_id': pid,
                'name': player_info.get('name', f"Player_{pid}"),
                'country': player_info.get('countryCode', 'Unknown'),
                'matches_played_with_team': matches_played,
                'attendance_percent': round((matches_played / total_team_matches) * 100, 1) if total_team_matches > 0 else 0
            })
        roster_details.sort(key=lambda x: x['matches_played_with_team'], reverse=True)
        
        subgraph = G.subgraph(roster_ids)
        
        # --- MODIFICATION: Create overall stats summary ---
        overall_stats = Counter()
        for mode, mode_stats in stats['stats_by_mode'].items():
            overall_stats['wins'] += mode_stats['wins']
            overall_stats['losses'] += mode_stats['losses']
            overall_stats['matches'] += mode_stats['matches']
        
        total_decided = overall_stats['wins'] + overall_stats['losses']
        overall_stats['win_rate'] = overall_stats['wins'] / total_decided if total_decided > 0 else 0.0

        analyzed_rosters.append({
            'roster_id': f"roster_{i+1}",
            'team_name': f"{roster_details[0]['name']}'s Squad",
            'player_count': len(roster_ids),
            'roster': roster_details,
            'stats_overall': dict(overall_stats),
            'stats_by_mode': stats['stats_by_mode'],
            'avg_connection_strength': round(subgraph.size(weight='weight') / subgraph.number_of_edges(), 2) if subgraph.number_of_edges() > 0 else 0,
            'most_common_lineups': [
                {'lineup_names': [player_lookup.get(pid, {}).get('name', f"Player_{pid}") for pid in lineup], 'count': count}
                for lineup, count in stats['most_common_lineups']
            ]
        })

    analyzed_rosters.sort(key=lambda x: x['stats_overall']['matches'], reverse=True)
    print(f"--> Successfully analyzed {len(analyzed_rosters)} final rosters.")
    return analyzed_rosters


def detect_overlapping_communities(G, min_community_size=MIN_ROSTER_SIZE, edge_weight_threshold=15):
    """
    Detect overlapping communities where players can belong to multiple groups.
    
    This approach identifies tight sub-groups that may overlap when players
    are bridges between different social circles.
    """
    print("Running overlapping community detection...")
    
    overlapping_communities = []
    
    # Step 1: Find all ego networks (local communities around each high-degree node)
    ego_communities = []
    
    # Get nodes sorted by weighted degree
    node_strengths = []
    for node in G.nodes():
        total_strength = sum(G[node][neighbor]['weight'] for neighbor in G.neighbors(node))
        node_strengths.append((node, total_strength, len(list(G.neighbors(node)))))
    
    # Focus on nodes with multiple strong connections
    high_degree_nodes = [node for node, strength, degree in node_strengths if degree >= 3 and strength >= 50]
    
    print(f"Analyzing {len(high_degree_nodes)} high-degree nodes for local communities...")
    
    for center_node in high_degree_nodes:
        # Find separate communities around this center node
        local_communities = find_local_communities_around_node(G, center_node, edge_weight_threshold)
        ego_communities.extend(local_communities)
    
    # Step 2: Add communities based on edge-weight clustering
    weight_based_communities = find_weight_based_communities(G, edge_weight_threshold)
    ego_communities.extend(weight_based_communities)
    
    # Step 3: Filter and deduplicate communities
    for community in ego_communities:
        if len(community) >= min_community_size and len(community) <= 15:
            # Check if this community is sufficiently novel
            is_novel = True
            for existing_comm in overlapping_communities:
                overlap = len(set(community) & set(existing_comm))
                overlap_ratio = overlap / min(len(community), len(existing_comm))
                if overlap_ratio > 0.6:  # Reduced threshold for more diversity
                    is_novel = False
                    break
            
            if is_novel:
                overlapping_communities.append(community)
    
    print(f"Found {len(overlapping_communities)} distinct overlapping communities")
    
    # Step 4: Consolidate teams with very high overlap (stricter for teams)
    overlapping_communities = consolidate_overlapping_communities(overlapping_communities, overlap_threshold=0.85)
    
    print(f"Final count after consolidation: {len(overlapping_communities)} teams")
    return overlapping_communities


def find_local_communities_around_node(G, center_node, edge_weight_threshold=15):
    """
    Find separate communities that include the center node by analyzing
    the local neighborhood structure.
    """
    local_communities = []
    
    # Get neighbors grouped by connection strength
    strong_neighbors = []
    medium_neighbors = []
    
    for neighbor in G.neighbors(center_node):
        weight = G[center_node][neighbor]['weight']
        if weight >= edge_weight_threshold:
            strong_neighbors.append(neighbor)
        elif weight >= 8:  # Medium strength connections
            medium_neighbors.append(neighbor)
    
    if len(strong_neighbors) < 2:
        return []
    
    # Find clusters among the strong neighbors
    neighbor_clusters = cluster_neighbors_by_mutual_connections(G, strong_neighbors + medium_neighbors, min_connection_weight=8)
    
    # Create communities by combining center node with each cluster
    for cluster in neighbor_clusters:
        if len(cluster) >= 2:  # Need at least 2 neighbors to form a meaningful community
            community = [center_node] + cluster
            # Add some medium neighbors if they're well connected to the cluster
            for med_neighbor in medium_neighbors:
                if med_neighbor not in cluster:
                    connections_to_cluster = sum(1 for member in cluster if G.has_edge(med_neighbor, member) and G[med_neighbor][member]['weight'] >= 5)
                    if connections_to_cluster >= 2 and len(community) < 10:
                        community.append(med_neighbor)
            
            if len(community) >= MIN_ROSTER_SIZE:
                local_communities.append(community)
    
    return local_communities


def cluster_neighbors_by_mutual_connections(G, neighbors, min_connection_weight=8):
    """
    Group neighbors into clusters based on their mutual connections.
    """
    clusters = []
    remaining = set(neighbors)
    
    while remaining:
        # Start a new cluster with the first remaining node
        seed = remaining.pop()
        cluster = [seed]
        
        # Find other neighbors that are well-connected to nodes in this cluster
        to_check = list(remaining)
        for candidate in to_check:
            connections_to_cluster = 0
            for cluster_member in cluster:
                if G.has_edge(candidate, cluster_member):
                    if G[candidate][cluster_member]['weight'] >= min_connection_weight:
                        connections_to_cluster += 1
            
            # Add to cluster if well-connected
            if connections_to_cluster >= 1:  # At least one strong connection to the cluster
                cluster.append(candidate)
                remaining.remove(candidate)
        
        if len(cluster) >= 2:
            clusters.append(cluster)
    
    return clusters


def find_weight_based_communities(G, edge_weight_threshold=15):
    """
    Find communities based on edge weight clustering.
    """
    communities = []
    
    # Create a subgraph with only high-weight edges
    high_weight_edges = [(u, v) for u, v, data in G.edges(data=True) if data['weight'] >= edge_weight_threshold]
    high_weight_graph = G.edge_subgraph(high_weight_edges)
    
    # Find connected components in this high-weight graph
    for component in nx.connected_components(high_weight_graph):
        if len(component) >= MIN_ROSTER_SIZE and len(component) <= 12:
            communities.append(list(component))
    
    return communities


def consolidate_overlapping_communities(communities, overlap_threshold=0.85):
    """
    Merge communities that have X% or more overlap into single communities.
    Uses iterative merging to handle chains of overlapping communities.
    
    Args:
        communities: List of communities (each community is a list of player IDs)
        overlap_threshold: If communities overlap by this percentage or more, merge them
    
    Returns:
        List of consolidated communities
    """
    print(f"Consolidating communities with >{overlap_threshold*100:.0f}% overlap...")
    
    if not communities:
        return []
    
    # Convert to sets for faster operations
    community_sets = [set(community) for community in communities]
    
    # Keep track of which communities have been merged
    merged = [False] * len(community_sets)
    consolidated = []
    
    for i, community_set in enumerate(community_sets):
        if merged[i]:
            continue
            
        # Start a new consolidated community
        current_consolidated = community_set.copy()
        merged[i] = True
        merges_made = True
        
        # Keep merging until no more merges are possible
        while merges_made:
            merges_made = False
            for j, other_community_set in enumerate(community_sets):
                if merged[j] or i == j:
                    continue
                
                # Calculate overlap ratio
                overlap = len(current_consolidated & other_community_set)
                smaller_size = min(len(current_consolidated), len(other_community_set))
                overlap_ratio = overlap / smaller_size if smaller_size > 0 else 0
                
                # If overlap is high enough, merge them
                if overlap_ratio >= overlap_threshold:
                    old_size = len(current_consolidated)
                    current_consolidated |= other_community_set
                    merged[j] = True
                    merges_made = True
                    print(f"  Merged community of {len(other_community_set)} players with existing group (overlap: {overlap_ratio:.1%}, new size: {len(current_consolidated)})")
        
        consolidated.append(list(current_consolidated))
    
    print(f"Consolidated {len(communities)} communities into {len(consolidated)} communities")
    return consolidated


def main():
    """Main analysis pipeline to run all steps."""
    data, players_data = load_data()
    if data is None:
        print("Halting execution due to data loading failure.")
        return

    roster_graph, party_info_list = build_roster_network(data)
    final_rosters = detect_and_analyze_rosters(roster_graph, party_info_list, players_data, data)

    # --- Summary and Save ---
    print("\n=== Analysis Complete: Top 5 Rosters Discovered ===")
    for roster in final_rosters[:5]:
        overall = roster['stats_overall']
        win_loss = f"{overall['wins']}W-{overall['losses']}L"
        print(f"\n--- {roster['team_name']} ({win_loss}) ---")
        print(f"  Players: {roster['player_count']} | Matches (Overall): {overall['matches']}")
        print("  Roster (sorted by attendance):")
        for player in roster['roster']:
            print(f"    - {player['name']} ({player['country']}): {player['attendance_percent']}% attendance ({player['matches_played_with_team']} games)")
        
        print("  Stats by Mode:")
        for mode, stats in roster['stats_by_mode'].items():
            print(f"    - {mode}: {stats['wins']}W-{stats['losses']}L ({stats['matches']} games, {stats['win_rate']:.1%} WR)")

    final_results = {
        "analysis_date": pd.Timestamp.now().isoformat(),
        "config": {
            "min_matches_for_connection": MIN_MATCHES_FOR_CONNECTION,
            "min_team_matches": MIN_TEAM_MATCHES,
            "min_roster_size": MIN_ROSTER_SIZE,
            "max_roster_size": MAX_ROSTER_SIZE
        },
        "summary": {
            "total_rosters_found": len(final_rosters)
        },
        "rosters": final_rosters
    }

    output_filename = os.path.join('data', 'roster_analysis_results.json')
    print(f"\nSaving detailed results to {output_filename}...")
    with open(output_filename, 'w') as f:
        json.dump(final_results, f, indent=2, default=int)  # Save final_results, not final_rosters

    print("Script finished successfully.")


if __name__ == "__main__":
    main()
