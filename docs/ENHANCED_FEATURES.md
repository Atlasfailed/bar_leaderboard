# BAR Leaderboard System - Enhanced Features
===============================================

This document describes the optional enhancements added to the BAR Leaderboard system for improved maintainability, monitoring, and configuration management.

## 🚀 New Features Overview

### 1. Master Pipeline Runner (`run_all_pipelines.py`)
A comprehensive orchestration tool that runs all pipelines in the correct order.

**Features:**
- ✅ Sequential execution of all three pipelines
- ✅ Dependency checking and intelligent refresh detection
- ✅ Comprehensive logging and progress tracking
- ✅ Dry-run mode for testing
- ✅ Force refresh option
- ✅ Detailed execution summaries

**Usage:**
```bash
# Run all pipelines with default settings
python run_all_pipelines.py

# Force refresh even if data is up to date
python run_all_pipelines.py --force-refresh

# See what would be executed without running
python run_all_pipelines.py --dry-run

# Custom minimum games threshold
python run_all_pipelines.py --min-games 100
```

### 2. Data Validation (`data_validation.py`)
Comprehensive data quality validation for all pipeline inputs and outputs.

**Features:**
- ✅ Input data validation (matches, players, match_players)
- ✅ Cross-dataset consistency checks
- ✅ Output data validation for each pipeline
- ✅ Detailed validation reports
- ✅ Warning vs error classification

**Validation Checks:**
- Required columns presence
- Data type validation
- Range and consistency checks
- Duplicate detection
- Cross-reference validation

### 3. Performance Monitoring (`performance_monitoring.py`)
Real-time performance tracking and profiling for all operations.

**Features:**
- ✅ Operation timing and memory usage tracking
- ✅ CPU utilization monitoring
- ✅ Records per second calculation
- ✅ Peak memory usage tracking
- ✅ Performance reports in JSON format
- ✅ Context manager and decorator support

**Usage:**
```python
# Context manager
with performance_monitor.monitor_operation("Data Loading"):
    data = load_large_dataset()

# Decorator
@performance_monitor.monitor_function("calculate_rankings")
def calculate_rankings(data):
    return process_data(data)
```

### 4. Configuration Management (`config_manager.py`)
Advanced configuration system supporting YAML/JSON files and environment-specific settings.

**Features:**
- ✅ YAML and JSON configuration file support
- ✅ Environment-specific configurations (dev/prod/test)
- ✅ Environment variable overrides
- ✅ Default configuration file discovery
- ✅ Configuration validation and summaries

**Configuration File Structure:**
```yaml
development:
  min_games_threshold: 50
  cache_duration_hours: 24
  enable_monitoring: true
  enable_validation: true
  log_level: "INFO"

production:
  min_games_threshold: 100
  cache_duration_hours: 6
  ssl_verify: true
  max_workers: 8
```

**Environment Variables:**
- `BAR_MIN_GAMES_THRESHOLD`: Override minimum games
- `BAR_CACHE_DURATION_HOURS`: Override cache duration
- `BAR_ENABLE_MONITORING`: Enable/disable monitoring
- `BAR_LOG_LEVEL`: Set logging level

## 📊 Enhanced Pipeline Features

### Updated `run_pipelinev2.py`
The leaderboard pipeline now includes:

**New Command-Line Options:**
```bash
python run_pipelinev2.py --config config.yaml --environment production
python run_pipelinev2.py --no-monitoring --no-validation
```

**Integrated Features:**
- ✅ Performance monitoring for all major operations
- ✅ Input and output data validation
- ✅ Configuration file support
- ✅ Automatic performance and validation reporting

### Integration with Other Pipelines
Similar enhancements can be applied to:
- `nation_ranking_pipeline.py`
- `team_analysis.py`

## 🔧 Installation and Setup

### 1. Install Additional Dependencies
The enhancements require additional packages:

```bash
# If using uv (recommended)
uv add psutil pyyaml

# Or with pip
pip install psutil pyyaml
```

### 2. Create Configuration File
Copy the example configuration:

```bash
cp config.example.yaml config.yaml
# Edit config.yaml as needed
```

### 3. Set Environment Variables (Optional)
```bash
export BAR_MIN_GAMES_THRESHOLD=100
export BAR_ENABLE_MONITORING=true
export BAR_LOG_LEVEL=INFO
```

## 📈 Usage Examples

### Running All Pipelines
```bash
# Basic execution
python run_all_pipelines.py

# Production environment with custom config
python run_all_pipelines.py --config config.yaml

# Testing with dry-run
python run_all_pipelines.py --dry-run --min-games 10
```

### Individual Pipeline with Enhancements
```bash
# With full monitoring and validation
python run_pipelinev2.py --config config.yaml --environment production

# Minimal execution for testing
python run_pipelinev2.py --no-monitoring --no-validation --min-games 5
```

### Performance Analysis
After running pipelines with monitoring enabled, check the performance reports:

```bash
ls data/performance_report_*.json
```

## 📋 Configuration Options

### Core Settings
- `min_games_threshold`: Minimum games for leaderboard inclusion
- `cache_duration_hours`: How long to cache downloaded data
- `max_workers`: Number of parallel workers
- `chunk_size`: Data processing chunk size

### Monitoring & Validation
- `enable_monitoring`: Enable performance monitoring
- `enable_validation`: Enable data validation
- `save_performance_reports`: Save performance reports to disk
- `save_validation_reports`: Save validation reports to disk

### Team Analysis
- `min_matches_for_connection`: Minimum matches to establish player connection
- `min_team_matches`: Minimum matches for team inclusion
- `min_roster_size`: Minimum players per roster
- `max_roster_size`: Maximum players per roster

### Network & Performance
- `ssl_verify`: Enable SSL certificate verification
- `request_timeout`: HTTP request timeout in seconds
- `log_level`: Logging level (DEBUG, INFO, WARNING, ERROR)

## 🎯 Benefits

### For Developers
- **Easier Debugging**: Comprehensive logging and validation
- **Performance Insights**: Detailed performance metrics
- **Flexible Configuration**: Environment-specific settings
- **Consistent Execution**: Master pipeline runner

### For Operations
- **Monitoring**: Real-time performance tracking
- **Reliability**: Data validation prevents bad outputs
- **Scalability**: Configurable resource usage
- **Automation**: One-command pipeline execution

### For Data Quality
- **Validation**: Comprehensive input/output checks
- **Consistency**: Cross-dataset validation
- **Monitoring**: Performance and quality metrics
- **Reporting**: Detailed validation and performance reports

## 🔍 Troubleshooting

### Missing Dependencies
If you see import errors for `psutil` or `yaml`:
```bash
uv add psutil pyyaml
# or
pip install psutil pyyaml
```

### Configuration Issues
To debug configuration problems:
```python
from config_manager import config_manager
config_manager.print_config_summary()
```

### Performance Issues
Check performance reports in the `data/` directory:
```bash
cat data/performance_report_*.json | jq '.performance_summary'
```

### Validation Failures
Enable detailed validation logging:
```bash
export BAR_LOG_LEVEL=DEBUG
python run_pipelinev2.py --config config.yaml
```

## 📚 API Reference

### Performance Monitoring
```python
from performance_monitoring import performance_monitor

# Monitor operation
with performance_monitor.monitor_operation("My Operation", records_count=1000):
    # Your code here
    pass

# Get summary
summary = performance_monitor.get_performance_summary()
performance_monitor.print_performance_summary()
```

### Data Validation
```python
from data_validation import data_validator

# Validate inputs
is_valid = data_validator.validate_datamart_inputs(raw_data)

# Validate outputs
is_valid = data_validator.validate_pipeline_output(results, 'leaderboard')

# Get summary
summary = data_validator.get_validation_summary()
data_validator.print_validation_summary()
```

### Configuration Management
```python
from config_manager import config_manager

# Load configuration
env_config = config_manager.load_configuration('config.yaml', 'production')

# Print summary
config_manager.print_config_summary()

# Create example config
config_manager.create_example_config()
```

---

**Note**: All enhancements are designed to be **optional** and **backward compatible**. Existing scripts will continue to work without modification, but can be enhanced by using the new features.
