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
    """
    # OPTIMIZATION: Use the inverted index to get a small, relevant subset of parties
    relevant_party_indices = {idx for pid in roster_ids for idx in player_to_party_map.get(pid, [])}
    
    team_match_info = []
    for idx in relevant_party_indices:
        party_info = party_info_list[idx]
        # Check if this party is a "team match" (>= 2 roster members present)
        if len(set(roster_ids).intersection(party_info['players'])) >= 2:
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
    
    # Build extended network for community detection (includes non-party connections)
    extended_G = build_extended_community_network(G, data, min_non_party_matches=20)
    
    # Store unrestricted communities for the "Communities" tab (use extended network)
    unrestricted_communities = []
    # Create communities using the extended network with relaxed parameters
    unrestricted_overlapping = detect_overlapping_communities_relaxed(extended_G, min_community_size=MIN_ROSTER_SIZE, edge_weight_threshold=6)
    
    # Apply additional merging for communities
    print(f"\n=== Additional Community Merging ===")
    print(f"Before merging: {len(unrestricted_overlapping)} communities")
    
    # First, merge communities with 65% similarity
    unrestricted_overlapping = merge_similar_communities(unrestricted_overlapping, similarity_threshold=0.65)
    
    # Then, merge small communities with connected larger ones
    unrestricted_overlapping = merge_small_communities_with_connected(unrestricted_overlapping, extended_G, min_size=10)
    
    for i, community in enumerate(unrestricted_overlapping):
        if len(community) >= MIN_ROSTER_SIZE:  # Only minimum size filter
            community_roster = []
            for pid in community:
                player_info = player_lookup.get(pid, {})
                community_roster.append({
                    'user_id': pid,
                    'name': player_info.get('name', f"Player_{pid}"),
                    'country': player_info.get('countryCode', 'Unknown')
                })
            
            community_roster.sort(key=lambda x: x['name'])
            unrestricted_communities.append({
                'community_id': f"community_{i+1}",
                'community_name': f"Community {i+1}",
                'player_count': len(community),
                'roster': community_roster
            })
    
    # Sort unrestricted communities by size (largest first)
    unrestricted_communities.sort(key=lambda x: x['player_count'], reverse=True)
    
    # Use overlapping communities for the main roster analysis
    rosters = []
    for community in overlapping_communities:
        if MIN_ROSTER_SIZE <= len(community) <= MAX_ROSTER_SIZE:
            rosters.append(community)
    
    print(f"Final count: {len(rosters)} potential core rosters to analyze from overlapping detection.")

    analyzed_rosters = []
    for i, roster_ids in enumerate(rosters):
        stats = calculate_roster_stats(roster_ids, party_info_list, player_to_party_map, match_win_lookup)
        
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
    return analyzed_rosters, unrestricted_communities


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


def detect_overlapping_communities_relaxed(G, min_community_size=MIN_ROSTER_SIZE, edge_weight_threshold=6):
    """
    Detect overlapping communities with more relaxed parameters for the Communities tab.
    This allows for larger communities and lower edge weight thresholds.
    """
    print(f"Running relaxed overlapping community detection (threshold={edge_weight_threshold})...")
    
    overlapping_communities = []
    
    # Step 1: Find all ego networks (local communities around each high-degree node)
    ego_communities = []
    
    # Get nodes sorted by weighted degree
    node_strengths = []
    for node in G.nodes():
        total_strength = sum(G[node][neighbor]['weight'] for neighbor in G.neighbors(node))
        node_strengths.append((node, total_strength, len(list(G.neighbors(node)))))
    
    # Focus on nodes with multiple connections (more relaxed than teams)
    high_degree_nodes = [node for node, strength, degree in node_strengths if degree >= 2 and strength >= 15]
    
    print(f"Analyzing {len(high_degree_nodes)} high-degree nodes for relaxed local communities...")
    
    for center_node in high_degree_nodes:
        # Find separate communities around this center node with relaxed parameters
        local_communities = find_local_communities_around_node_relaxed(G, center_node, edge_weight_threshold)
        ego_communities.extend(local_communities)
    
    # Step 2: Add communities based on edge-weight clustering with relaxed threshold
    weight_based_communities = find_weight_based_communities_relaxed(G, edge_weight_threshold)
    ego_communities.extend(weight_based_communities)
    
    # Step 3: Filter and deduplicate communities (no max size limit)
    for community in ego_communities:
        if len(community) >= min_community_size:  # No upper size limit
            # Check if this community is sufficiently novel (more relaxed overlap tolerance)
            is_novel = True
            for existing_comm in overlapping_communities:
                overlap = len(set(community) & set(existing_comm))
                overlap_ratio = overlap / min(len(community), len(existing_comm))
                if overlap_ratio > 0.6:  # Higher threshold = more overlap allowed
                    is_novel = False
                    break
            
            if is_novel:
                overlapping_communities.append(community)
    
    print(f"Found {len(overlapping_communities)} distinct relaxed overlapping communities")
    
    # Step 4: Consolidate communities with high overlap
    overlapping_communities = consolidate_overlapping_communities(overlapping_communities, overlap_threshold=0.80)
    
    print(f"Final count after consolidation: {len(overlapping_communities)} communities")
    return overlapping_communities


def find_local_communities_around_node_relaxed(G, center_node, edge_weight_threshold=6):
    """
    Find separate communities that include the center node with relaxed parameters.
    """
    local_communities = []
    
    # Get neighbors grouped by connection strength (more relaxed thresholds)
    strong_neighbors = []
    medium_neighbors = []
    
    for neighbor in G.neighbors(center_node):
        weight = G[center_node][neighbor]['weight']
        if weight >= edge_weight_threshold:
            strong_neighbors.append(neighbor)
        elif weight >= 3:  # Lower threshold for medium connections
            medium_neighbors.append(neighbor)
    
    if len(strong_neighbors) < 1:  # Only need 1 strong neighbor
        return []
    
    # Find clusters among the neighbors (include medium neighbors)
    all_neighbors = strong_neighbors + medium_neighbors
    neighbor_clusters = cluster_neighbors_by_mutual_connections(G, all_neighbors, min_connection_weight=3)
    
    # Create communities by combining center node with each cluster
    for cluster in neighbor_clusters:
        if len(cluster) >= 1:  # More relaxed - only need 1 neighbor
            community = [center_node] + cluster
            
            # Add additional neighbors if they're reasonably connected
            remaining_neighbors = [n for n in all_neighbors if n not in cluster]
            for neighbor in remaining_neighbors:
                connections_to_cluster = sum(1 for member in cluster if G.has_edge(neighbor, member) and G[neighbor][member]['weight'] >= 2)
                if connections_to_cluster >= 1:  # No size limit
                    community.append(neighbor)
            
            if len(community) >= MIN_ROSTER_SIZE:
                local_communities.append(community)
    
    return local_communities


def find_weight_based_communities_relaxed(G, edge_weight_threshold=6):
    """
    Find communities based on edge weight clustering with relaxed parameters.
    """
    communities = []
    
    # Create a subgraph with only medium-weight edges (lower threshold)
    medium_weight_edges = [(u, v) for u, v, data in G.edges(data=True) if data['weight'] >= edge_weight_threshold]
    medium_weight_graph = G.edge_subgraph(medium_weight_edges)
    
    # Find connected components in this medium-weight graph
    for component in nx.connected_components(medium_weight_graph):
        if len(component) >= MIN_ROSTER_SIZE:  # No upper size limit
            communities.append(list(component))
    
    return communities


def consolidate_overlapping_communities(communities, overlap_threshold=0.80):
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


def merge_small_communities_with_connected(communities, G, min_size=10):
    """
    Merge communities with fewer than min_size players with other communities
    they are well-connected to.
    
    Args:
        communities: List of communities (each is a list of player IDs)
        G: The network graph to check connections
        min_size: Minimum community size threshold
    
    Returns:
        List of communities after merging small ones
    """
    print(f"Merging communities with < {min_size} players with connected communities...")
    
    if not communities:
        return communities
    
    # Convert to sets for easier operations and track original indices
    community_data = [(i, set(community)) for i, community in enumerate(communities)]
    
    # Separate small and large communities
    small_communities = [(i, community_set) for i, community_set in community_data if len(community_set) < min_size]
    large_communities = [(i, community_set) for i, community_set in community_data if len(community_set) >= min_size]
    
    print(f"Found {len(small_communities)} small communities and {len(large_communities)} large communities")
    
    # Start with all large communities
    merged_communities = [list(community_set) for _, community_set in large_communities]
    merged_small_indices = set()
    
    # Try to merge each small community with the best-connected large community
    for small_idx, small_community in small_communities:
        if small_idx in merged_small_indices:
            continue
            
        best_target_idx = None
        best_connection_strength = 0
        
        # Find the large community with the strongest connections
        for target_idx, (large_idx, large_community) in enumerate(large_communities):
            # Calculate connection strength between communities
            connection_strength = 0
            connection_count = 0
            
            for small_player in small_community:
                for large_player in large_community:
                    if G.has_edge(small_player, large_player):
                        connection_strength += G[small_player][large_player]['weight']
                        connection_count += 1
            
            # Normalize by the smaller community size to avoid bias toward large communities
            normalized_strength = connection_strength / len(small_community) if len(small_community) > 0 else 0
            
            if normalized_strength > best_connection_strength and normalized_strength > 2.0:  # Minimum threshold
                best_connection_strength = normalized_strength
                best_target_idx = target_idx
        
        if best_target_idx is not None:
            # Merge with the best target
            old_size = len(merged_communities[best_target_idx])
            merged_communities[best_target_idx] = list(set(merged_communities[best_target_idx]) | small_community)
            merged_small_indices.add(small_idx)
            print(f"  Merged small community of {len(small_community)} players with large community of {old_size} players (connection strength: {best_connection_strength:.1f})")
        else:
            # No good merge target found, keep as separate community if it meets minimum size
            if len(small_community) >= MIN_ROSTER_SIZE:
                merged_communities.append(list(small_community))
    
    print(f"After merging: {len(merged_communities)} communities")
    return merged_communities


def merge_similar_communities(communities, similarity_threshold=0.65):
    """
    Merge communities that have >= similarity_threshold overlap.
    This is more aggressive than the consolidation function.
    
    Args:
        communities: List of communities (each is a list of player IDs)
        similarity_threshold: Minimum similarity ratio to merge communities
    
    Returns:
        List of communities after merging similar ones
    """
    print(f"Merging communities with ≥{similarity_threshold*100:.0f}% similarity...")
    
    if not communities:
        return []
    
    # Convert to sets for faster operations
    community_sets = [set(community) for community in communities]
    
    # Keep track of which communities have been merged
    merged = [False] * len(community_sets)
    merged_communities = []
    
    for i, community_set in enumerate(community_sets):
        if merged[i]:
            continue
            
        # Start a new merged community
        current_merged = community_set.copy()
        merged[i] = True
        merges_made = True
        
        # Keep merging until no more merges are possible
        while merges_made:
            merges_made = False
            for j, other_community_set in enumerate(community_sets):
                if merged[j] or i == j:
                    continue
                
                # Calculate similarity (Jaccard similarity)
                intersection = len(current_merged & other_community_set)
                union = len(current_merged | other_community_set)
                similarity = intersection / union if union > 0 else 0
                
                # If similarity is high enough, merge them
                if similarity >= similarity_threshold:
                    old_size = len(current_merged)
                    current_merged |= other_community_set
                    merged[j] = True
                    merges_made = True
                    print(f"  Merged community of {len(other_community_set)} players with existing group (similarity: {similarity:.1%}, new size: {len(current_merged)})")
        
        merged_communities.append(list(current_merged))
    
    print(f"Merged {len(communities)} communities into {len(merged_communities)} communities")
    return merged_communities


def build_extended_community_network(G, data, min_non_party_matches=20):
    """
    Extends the party-based network with additional connections based on players
    who have played together frequently, even without being in a party.
    This is used specifically for community detection (not teams).
    
    Args:
        G: The original party-based network
        data: The full match data
        min_non_party_matches: Minimum number of non-party matches to create a connection
    
    Returns:
        Extended graph for community detection
    """
    print(f"\n=== Building Extended Network for Communities ===")
    print(f"Adding connections for players who played {min_non_party_matches}+ games together (non-party)")
    
    # Create a copy of the original graph
    extended_G = G.copy()
    
    # Count matches where players were on the same team (regardless of party)
    same_team_matches = defaultdict(int)
    
    # Group by match_id and team_id to find players on the same team
    team_groups = data.groupby(['match_id', 'team_id'])['user_id'].apply(list)
    
    for (match_id, team_id), players in team_groups.items():
        if len(players) > 1:
            # Count all pairs of players on the same team
            for pair in combinations(players, 2):
                # Sort pair to ensure consistent ordering
                sorted_pair = tuple(sorted(pair))
                same_team_matches[sorted_pair] += 1
    
    print(f"Found {len(same_team_matches):,} unique player pairings from same-team matches.")
    
    # Add new edges for non-party connections that meet the threshold
    new_connections = 0
    for (player1, player2), match_count in same_team_matches.items():
        if match_count >= min_non_party_matches:
            # If there's already a party-based connection, don't override it
            if not extended_G.has_edge(player1, player2):
                # Use a lower weight for non-party connections to distinguish them
                extended_G.add_edge(player1, player2, weight=match_count // 3)  # Reduced weight
                new_connections += 1
    
    print(f"--> Added {new_connections} new connections based on non-party gameplay")
    print(f"--> Extended Network: {extended_G.number_of_nodes():,} players and {extended_G.number_of_edges():,} total connections.")
    
    return extended_G


def main():
    """Main analysis pipeline to run all steps."""
    data, players_data = load_data()
    if data is None:
        print("Halting execution due to data loading failure.")
        return

    roster_graph, party_info_list = build_roster_network(data)
    final_rosters, unrestricted_communities = detect_and_analyze_rosters(roster_graph, party_info_list, players_data, data)

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
            "total_rosters_found": len(final_rosters),
            "total_communities_found": len(unrestricted_communities)
        },
        "rosters": final_rosters,
        "communities": unrestricted_communities
    }

    output_filename = os.path.join('data', 'roster_analysis_results.json')
    print(f"\nSaving detailed results to {output_filename}...")
    with open(output_filename, 'w') as f:
        json.dump(final_results, f, indent=2, default=int)  # Save final_results, not final_rosters

    print("Script finished successfully.")


if __name__ == "__main__":
    main()
