#!/bin/bash

# Local pipeline runner script
# Run this script locally to generate data files, then upload them to PythonAnywhere

echo "Starting nation ranking pipeline..."

# Run the pipeline
python nation_ranking_pipeline.py

if [ $? -eq 0 ]; then
    echo "Pipeline completed successfully!"
    echo ""
    echo "Generated files to upload to PythonAnywhere:"
    echo "- data/nation_rankings.parquet"
    echo "- data/player_contributions.parquet" 
    echo "- data/iso_country.csv"
    echo "- data/final_leaderboard.parquet"
    echo ""
    echo "Next steps:"
    echo "1. Upload these data files to your PythonAnywhere /home/yourusername/nation_leaderboard/data/ directory"
    echo "2. Upload your Flask app files to PythonAnywhere"
    echo "3. Configure the web app on PythonAnywhere dashboard"
else
    echo "Pipeline failed. Check the error messages above."
fi
