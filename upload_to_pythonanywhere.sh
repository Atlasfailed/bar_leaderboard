#!/bin/bash

# Upload script for PythonAnywhere (optional)
# This script can help automate uploading data files to PythonAnywhere
# You'll need to configure it with your PythonAnywhere credentials

echo "PythonAnywhere Upload Script"
echo "This is a template - you'll need to customize it for your setup"
echo ""

# Configuration (update these with your details)
PYTHONANYWHERE_USERNAME="yourusername"  # Replace with your PythonAnywhere username
REMOTE_PATH="/home/$PYTHONANYWHERE_USERNAME/nation_leaderboard/data/"

echo "Data files to upload:"
echo "- data/nation_rankings.parquet"
echo "- data/player_contributions.parquet"
echo "- data/final_leaderboard.parquet"
echo "- data/iso_country.csv"
echo ""

echo "Upload methods:"
echo "1. Use PythonAnywhere Files tab (manual, recommended for beginners)"
echo "2. Use rsync/scp (requires SSH, paid accounts only)"
echo "3. Use git (if you commit data files to your repository)"
echo ""

echo "For manual upload:"
echo "1. Go to https://www.pythonanywhere.com/user/$PYTHONANYWHERE_USERNAME/files/home/$PYTHONANYWHERE_USERNAME/nation_leaderboard/data/"
echo "2. Upload the data files listed above"
echo "3. Reload your web app from the Web tab"
echo ""

# Example for paid accounts with SSH access:
# echo "For automated upload (paid accounts only):"
# echo "scp data/*.parquet data/*.csv $PYTHONANYWHERE_USERNAME@ssh.pythonanywhere.com:$REMOTE_PATH"
