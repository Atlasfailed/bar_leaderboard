# PythonAnywhere Deployment Guide

## Overview
This guide helps you deploy your BAR Nation Leaderboard to PythonAnywhere free hosting. You'll run the data pipeline locally and upload the generated files to PythonAnywhere.

## Prerequisites
- PythonAnywhere free account (sign up at https://www.pythonanywhere.com)
- Local Python environment with project dependencies

## Step-by-Step Setup

### 1. Local Pipeline Setup

First, run the pipeline locally to generate the data files:

```bash
# Make sure you're in the project directory
cd /Users/gerthuybrechts/pyprojects/nation_leaderboard

# Run the pipeline locally
./run_pipeline_local.sh
# OR manually:
python nation_ranking_pipeline.py
```

This will generate the required data files in the `data/` directory:
- `nation_rankings.parquet`
- `player_contributions.parquet`
- `iso_country.csv` 
- `final_leaderboard.parquet`

### 2. PythonAnywhere Account Setup

1. Sign up for a free account at https://www.pythonanywhere.com
2. Go to your Dashboard
3. Open a Bash console from the "Tasks" menu

### 3. Upload Files to PythonAnywhere

You have two main approaches for getting your code to PythonAnywhere:

#### Option A: Manual Upload (Recommended for beginners)
1. Go to the "Files" tab in your PythonAnywhere dashboard
2. Create a new directory: `nation_leaderboard`
3. Upload the following files and directories:
   - `app.py` ⚠️ **CRITICAL: Make sure this is the updated version with all API endpoints**
   - `wsgi.py`
   - `requirements.txt`
   - `static/` (entire directory, including `js/player-leaderboard.js`)
   - `templates/` (entire directory, including `index.html`)
   - `data/` (the generated data files, especially `final_leaderboard.parquet`)

#### Option B: Git-based Deployment (Recommended for developers)

**Step 1: Set up Git locally (one-time setup)**
```bash
# In your project directory
git init
git add app.py wsgi.py requirements.txt *.md *.sh
git add static/ templates/
git commit -m "Initial commit"

# Push to GitHub (create repo first on github.com)
git remote add origin https://github.com/yourusername/nation_leaderboard.git
git push -u origin main
```

**Step 2: Deploy via Git on PythonAnywhere**
In a PythonAnywhere Bash console:
```bash
# Clone your repository
git clone https://github.com/yourusername/nation_leaderboard.git nation_leaderboard
cd nation_leaderboard
```

**Step 3: Upload data files separately**
- Git handles your code, but data files are uploaded manually via Files tab
- Upload `data/*.parquet` files to `/home/yourusername/nation_leaderboard/data/`
- This separation is intentional - code vs. data have different update cycles

**Benefits of Git approach:**
- ✅ Version control for your code
- ✅ Easy updates: `git pull` to get code changes
- ✅ Backup and collaboration
- ✅ Separates code (small, versioned) from data (large, frequently updated)

### 4. Install Dependencies

In a PythonAnywhere Bash console:

```bash
cd nation_leaderboard
pip3.10 install --user -r requirements.txt
```

### 5. Configure Web App

1. Go to the "Web" tab in your PythonAnywhere dashboard
2. Click "Add a new web app"
3. Choose "Manual configuration" (don't use the Flask wizard)
4. Choose Python 3.10
5. In the "Code" section:
   - Set "Source code" to: `/home/yourusername/nation_leaderboard`
   - Set "WSGI configuration file" to: `/home/yourusername/nation_leaderboard/wsgi.py`

### 6. Update WSGI Configuration

Edit the WSGI file in PythonAnywhere:
1. Go to the "Web" tab
2. Click on the WSGI configuration file link
3. Replace the contents with the content from your local `wsgi.py` file
4. **Important**: Update the path in `wsgi.py` to match your PythonAnywhere username:
   ```python
   path = '/home/YOURUSERNAME/nation_leaderboard'  # Replace YOURUSERNAME
   ```

### 7. Configure Static Files

In the "Web" tab, under "Static files":
- URL: `/static/`
- Directory: `/home/yourusername/nation_leaderboard/static/`

### 8. Test Your App

1. Click "Reload" in the Web tab
2. Visit your app at: `https://yourusername.pythonanywhere.com`

## Updating Your App

### Code Updates (if using Git)
To update your Flask application code:

```bash
# On PythonAnywhere, in your project directory
git pull origin main

# Reload your web app in the Web tab
```

### Data Updates (always manual)
To update the leaderboard data:

1. Run the pipeline locally: `./run_pipeline_local.sh`
2. Upload the new data files to PythonAnywhere via Files tab:
   - `data/nation_rankings.parquet`
   - `data/player_contributions.parquet`
   - `data/final_leaderboard.parquet`
3. Reload your web app in the PythonAnywhere Web tab

**Why separate code and data updates?**
- Code changes are infrequent, small, and benefit from version control
- Data updates are frequent, large files that change based on game activity
- This separation keeps your Git repo clean and fast

## Automation Options

### Option 1: Local Cron Job (Recommended)
Set up a local cron job to run the pipeline and automatically upload data:

```bash
# Edit crontab
crontab -e

# Add this line to run every hour:
0 * * * * cd /Users/gerthuybrechts/pyprojects/nation_leaderboard && ./run_pipeline_local.sh && ./upload_to_pythonanywhere.sh
```

### Option 2: PythonAnywhere Scheduled Tasks (Paid feature)
If you upgrade to a paid account, you can run the pipeline directly on PythonAnywhere.

## Troubleshooting

### Common Issues:

1. **Import Errors**: Make sure all dependencies are installed with `pip3.10 install --user -r requirements.txt`

2. **File Not Found**: Check that all data files are uploaded and paths are correct

3. **WSGI Errors**: Ensure the path in `wsgi.py` matches your actual PythonAnywhere username

4. **Static Files Not Loading**: Verify the static files configuration in the Web tab

5. **"Could not connect to backend" on index page**: This means you're missing API endpoints. Make sure you upload the **latest version** of `app.py` that includes:
   - `/api/status`
   - `/api/leaderboards` 
   - `/api/leaderboard/<leaderboard_id>/<game_type>`
   - `/api/leaderboard/global/<game_type>`

6. **Player leaderboard shows "Loading..." forever**: Check that:
   - `static/js/player-leaderboard.js` is uploaded and uses relative URLs (not hardcoded domain)
   - `data/final_leaderboard.parquet` is uploaded
   - API endpoints are working (test: `https://yourusername.pythonanywhere.com/api/status`)

### Checking Logs:
- Error logs: Web tab → Error log
- Server logs: Web tab → Server log

## Free Account Limitations

PythonAnywhere free accounts have some limitations:
- One web app only
- Limited CPU seconds per day
- No scheduled tasks
- HTTPS only for pythonanywhere.com subdomain

## Your App URLs

Once deployed, your app will be available at:
- Main site: `https://yourusername.pythonanywhere.com`
- Nation rankings: `https://yourusername.pythonanywhere.com/nation-rankings`
- API endpoints: `https://yourusername.pythonanywhere.com/api/...`
