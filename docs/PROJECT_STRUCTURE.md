# BAR Leaderboard - Reorganized Project Structure
===============================================

## 📁 Project Layout

```
bar_leaderboard/
├── 📁 src/                          # Source code
│   ├── 📁 core/                     # Core functionality
│   │   ├── config.py                # Centralized configuration
│   │   ├── utils.py                 # Shared utilities
│   │   ├── config_manager.py        # Configuration file management
│   │   └── __init__.py
│   │
│   ├── 📁 pipelines/                # Data processing pipelines
│   │   ├── run_pipelinev2.py        # Main leaderboard calculation
│   │   ├── nation_ranking_pipeline.py # Nation rankings
│   │   ├── team_analysis.py         # Team formation analysis
│   │   ├── run_all_pipelines.py     # Master orchestration
│   │   └── __init__.py
│   │
│   ├── 📁 monitoring/               # Monitoring and validation
│   │   ├── data_validation.py       # Data quality validation
│   │   ├── performance_monitoring.py # Performance tracking
│   │   └── __init__.py
│   │
│   ├── 📁 web/                      # Web application
│   │   ├── app.py                   # Flask application
│   │   ├── wsgi.py                  # WSGI entry point
│   │   ├── 📁 static/               # CSS, JS, images
│   │   ├── 📁 templates/            # HTML templates
│   │   └── __init__.py
│   │
│   └── __init__.py
│
├── 📁 config/                       # Configuration files
│   └── config.example.yaml          # Example configuration
│
├── 📁 docs/                         # Documentation
│   ├── ENHANCED_FEATURES.md         # Feature documentation
│   ├── PROJECT_STATUS.md            # Project status
│   ├── DEPLOYMENT_GUIDE.md          # Deployment guide
│   ├── README.md                    # Main documentation
│   ├── README_DEPLOYMENT.md         # Deployment README
│   └── debug_test.html              # Debug files
│
├── 📁 scripts/                      # Utility scripts
│   └── test.py                      # Test script
│
├── 📁 data/                         # Data files
│   ├── *.parquet                    # Generated data files
│   ├── *.csv                        # Input data files
│   └── replays/                     # Replay data
│
├── 🚀 Entry Points (Root Level)     # Easy-to-use entry points
├── run_leaderboard.py               # → src/pipelines/run_pipelinev2.py
├── run_nation_rankings.py           # → src/pipelines/nation_ranking_pipeline.py
├── run_team_analysis.py             # → src/pipelines/team_analysis.py
├── run_all_pipelines.py             # → src/pipelines/run_all_pipelines.py
├── app.py                           # → src/web/app.py
├── wsgi.py                          # → src/web/wsgi.py
│
└── 📋 Project Files
    ├── pyproject.toml               # Python project configuration
    ├── requirements.txt             # Dependencies
    ├── uv.lock                      # Dependency lock file
    └── .gitignore                   # Git ignore patterns
```

## 🏗️ Architecture Benefits

### 1. **Logical Organization**
- **Core**: Fundamental functionality (config, utils, management)
- **Pipelines**: Data processing workflows
- **Monitoring**: Validation and performance tracking
- **Web**: Flask application and assets
- **Config**: Environment-specific settings
- **Docs**: All documentation in one place
- **Scripts**: Utility and test scripts

### 2. **Clean Imports**
- Relative imports within packages (`from ..core.config import config`)
- Clear module hierarchy
- Reduced import path complexity

### 3. **Easy Entry Points**
- Root-level scripts for common operations
- No need to navigate into src/ for basic usage
- Backward compatibility maintained

### 4. **Scalability**
- Easy to add new pipeline modules
- Clear separation of concerns
- Modular design supports growth

### 5. **Development Workflow**
- Source code isolated in `src/`
- Documentation centralized
- Configuration externalized
- Scripts and entry points at root for convenience

## 🚀 Usage Examples

### Running Pipelines
```bash
# Individual pipelines
python run_leaderboard.py --min-games 10
python run_nation_rankings.py --min-games 5
python run_team_analysis.py --min-matches 5

# All pipelines
python run_all_pipelines.py --dry-run
python run_all_pipelines.py --force-refresh
```

### Web Application
```bash
# Development server
python app.py

# Production deployment (use wsgi.py)
gunicorn wsgi:application
```

### Direct Module Access
```bash
# Access modules directly if needed
python -m src.pipelines.run_pipelinev2 --help
python -m src.web.app
```

## 🔧 Migration Notes

### Updated Import Paths
- `from config import config` → `from ..core.config import config`
- `from utils import setup_logging` → `from ..core.utils import setup_logging`
- `from data_validation import data_validator` → `from ..monitoring.data_validation import data_validator`

### Entry Points
All root-level entry points automatically handle the Python path setup, so users don't need to worry about module imports.

### Backward Compatibility
The new structure maintains all functionality while providing a much cleaner organization for long-term maintenance and development.

## 📦 Installation & Setup

1. Install dependencies: `uv sync`
2. Copy configuration: `cp config/config.example.yaml config/config.yaml`
3. Run pipelines: `python run_all_pipelines.py`
4. Start web app: `python app.py`

The reorganized structure provides a professional, maintainable foundation for the BAR Leaderboard system! 🎉
