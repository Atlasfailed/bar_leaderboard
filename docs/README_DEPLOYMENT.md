# BAR Nation Leaderboard - PythonAnywhere Deployment

## Quick Start

### 1. Generate Data Locally
```bash
./run_pipeline_local.sh
```

### 2. Upload to PythonAnywhere
- Upload all project files to `/home/yourusername/nation_leaderboard/`
- Upload generated data files to `/home/yourusername/nation_leaderboard/data/`
- Configure web app to use `wsgi.py`

### 3. Install Dependencies
```bash
pip3.10 install --user -r requirements.txt
```

### 4. Access Your App
Visit: `https://yourusername.pythonanywhere.com`

## Files for PythonAnywhere

### Core Application Files:
- `app.py` - Main Flask application
- `wsgi.py` - WSGI configuration for PythonAnywhere
- `requirements.txt` - Python dependencies
- `static/` - CSS, JavaScript, images
- `templates/` - HTML templates

### Data Files (generated locally):
- `data/nation_rankings.parquet`
- `data/player_contributions.parquet` 
- `data/final_leaderboard.parquet`
- `data/iso_country.csv`

### Optional:
- `run_pipeline_local.sh` - Local pipeline runner
- `upload_to_pythonanywhere.sh` - Upload helper script
- `DEPLOYMENT_GUIDE.md` - Detailed deployment instructions

## Important Notes

1. **Update WSGI path**: Edit `wsgi.py` and replace `yourusername` with your actual PythonAnywhere username
2. **Data refresh**: Re-run pipeline locally and upload new data files when you want to update the leaderboard
3. **Free account limits**: PythonAnywhere free accounts have CPU time limits
4. **Static files**: Configure static file serving in PythonAnywhere Web tab

## Support

- PythonAnywhere Help: https://help.pythonanywhere.com/
- Flask Documentation: https://flask.palletsprojects.com/
