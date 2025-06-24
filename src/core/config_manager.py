#!/usr/bin/env python3
"""
BAR Leaderboard Configuration File Support
==========================================

Extended configuration system that supports loading settings from YAML/JSON files
and environment-specific configurations.
"""

import os
import yaml
import json
from pathlib import Path
from typing import Dict, Any, Optional, Union
from dataclasses import dataclass, asdict

from config import config as base_config
from utils import setup_logging

@dataclass
class EnvironmentConfig:
    """Environment-specific configuration settings."""
    # Data sources
    cache_duration_hours: int = 24
    max_workers: int = 4
    chunk_size: int = 10000
    
    # Analysis parameters
    min_games_threshold: int = 50
    k_factor_base: float = 400.0
    
    # Team analysis
    min_matches_for_connection: int = 5
    min_team_matches: int = 10
    min_roster_size: int = 2
    max_roster_size: int = 10
    
    # Performance
    enable_monitoring: bool = True
    enable_validation: bool = True
    log_level: str = "INFO"
    
    # Network
    ssl_verify: bool = False
    request_timeout: int = 30
    
    # Output formats
    save_performance_reports: bool = True
    save_validation_reports: bool = True

class ConfigurationManager:
    """Manages configuration loading from multiple sources."""
    
    def __init__(self):
        self.logger = setup_logging(self.__class__.__name__)
        self.env_config: Optional[EnvironmentConfig] = None
        self.config_file_path: Optional[Path] = None
    
    def load_configuration(self, config_file: Optional[Union[str, Path]] = None, 
                          environment: str = "development") -> EnvironmentConfig:
        """Load configuration from file and environment variables."""
        
        # Start with default configuration
        env_config = EnvironmentConfig()
        
        # Try to load from config file
        if config_file:
            env_config = self._load_from_file(config_file, environment, env_config)
        else:
            # Look for default config files
            for default_file in self._get_default_config_files():
                if default_file.exists():
                    self.logger.info(f"Found default config file: {default_file}")
                    env_config = self._load_from_file(default_file, environment, env_config)
                    break
        
        # Override with environment variables
        env_config = self._load_from_environment(env_config)
        
        # Apply configuration to base config
        self._apply_to_base_config(env_config)
        
        self.env_config = env_config
        self.logger.info(f"Configuration loaded for environment: {environment}")
        
        return env_config
    
    def _get_default_config_files(self) -> list[Path]:
        """Get list of default configuration file locations."""
        base_dir = Path(__file__).parent
        return [
            base_dir / "config.yaml",
            base_dir / "config.yml", 
            base_dir / "config.json",
            base_dir / ".bar_config.yaml",
            Path.home() / ".bar_leaderboard" / "config.yaml"
        ]
    
    def _load_from_file(self, config_file: Union[str, Path], 
                       environment: str, base_env_config: EnvironmentConfig) -> EnvironmentConfig:
        """Load configuration from a YAML or JSON file."""
        config_path = Path(config_file)
        
        if not config_path.exists():
            self.logger.warning(f"Config file not found: {config_path}")
            return base_env_config
        
        try:
            with open(config_path, 'r') as f:
                if config_path.suffix.lower() in ['.yaml', '.yml']:
                    config_data = yaml.safe_load(f)
                elif config_path.suffix.lower() == '.json':
                    config_data = json.load(f)
                else:
                    self.logger.error(f"Unsupported config file format: {config_path.suffix}")
                    return base_env_config
            
            # Extract environment-specific config
            env_data = config_data.get(environment, {})
            if not env_data and environment != 'default':
                env_data = config_data.get('default', {})
            
            # Update base config with file data
            env_config_dict = asdict(base_env_config)
            env_config_dict.update(env_data)
            
            self.config_file_path = config_path
            self.logger.info(f"Loaded config from {config_path} (environment: {environment})")
            
            return EnvironmentConfig(**env_config_dict)
            
        except Exception as e:
            self.logger.error(f"Failed to load config from {config_path}: {e}")
            return base_env_config
    
    def _load_from_environment(self, env_config: EnvironmentConfig) -> EnvironmentConfig:
        """Override configuration with environment variables."""
        env_mapping = {
            'BAR_CACHE_DURATION_HOURS': ('cache_duration_hours', int),
            'BAR_MAX_WORKERS': ('max_workers', int),
            'BAR_MIN_GAMES_THRESHOLD': ('min_games_threshold', int),
            'BAR_K_FACTOR_BASE': ('k_factor_base', float),
            'BAR_MIN_MATCHES_CONNECTION': ('min_matches_for_connection', int),
            'BAR_MIN_TEAM_MATCHES': ('min_team_matches', int),
            'BAR_ENABLE_MONITORING': ('enable_monitoring', bool),
            'BAR_ENABLE_VALIDATION': ('enable_validation', bool),
            'BAR_LOG_LEVEL': ('log_level', str),
            'BAR_SSL_VERIFY': ('ssl_verify', bool),
        }
        
        env_config_dict = asdict(env_config)
        
        for env_var, (config_key, config_type) in env_mapping.items():
            env_value = os.getenv(env_var)
            if env_value is not None:
                try:
                    if config_type == bool:
                        env_config_dict[config_key] = env_value.lower() in ('true', '1', 'yes', 'on')
                    else:
                        env_config_dict[config_key] = config_type(env_value)
                    self.logger.info(f"Environment override: {config_key} = {env_config_dict[config_key]}")
                except ValueError as e:
                    self.logger.warning(f"Invalid environment value for {env_var}: {env_value} ({e})")
        
        return EnvironmentConfig(**env_config_dict)
    
    def _apply_to_base_config(self, env_config: EnvironmentConfig) -> None:
        """Apply environment configuration to the base config object."""
        # Update analysis config
        base_config.analysis.min_games_threshold = env_config.min_games_threshold
        base_config.analysis.k_factor_base = env_config.k_factor_base
        base_config.analysis.min_matches_for_connection = env_config.min_matches_for_connection
        base_config.analysis.min_team_matches = env_config.min_team_matches
        base_config.analysis.min_roster_size = env_config.min_roster_size
        base_config.analysis.max_roster_size = env_config.max_roster_size
        base_config.analysis.max_workers = env_config.max_workers
        base_config.analysis.chunk_size = env_config.chunk_size
        
        # Update datamart config
        base_config.datamart.cache_duration_hours = env_config.cache_duration_hours
        
        # Update network config
        base_config.network.ssl_verify = env_config.ssl_verify
    
    def create_example_config(self, output_path: Optional[Path] = None) -> Path:
        """Create an example configuration file."""
        if output_path is None:
            output_path = Path(__file__).parent / "config.example.yaml"
        
        example_config = {
            "# BAR Leaderboard Configuration": None,
            "# Environment-specific settings": None,
            "development": asdict(EnvironmentConfig()),
            "production": {
                **asdict(EnvironmentConfig()),
                "cache_duration_hours": 6,
                "enable_monitoring": True,
                "enable_validation": True,
                "log_level": "INFO",
                "min_games_threshold": 100,
                "ssl_verify": True
            },
            "testing": {
                **asdict(EnvironmentConfig()),
                "cache_duration_hours": 1,
                "min_games_threshold": 5,
                "max_workers": 2,
                "enable_monitoring": False
            }
        }
        
        # Remove None values (comments)
        clean_config = {k: v for k, v in example_config.items() if v is not None}
        
        with open(output_path, 'w') as f:
            yaml.dump(clean_config, f, default_flow_style=False, sort_keys=False)
        
        self.logger.info(f"Example configuration created: {output_path}")
        return output_path
    
    def get_current_config_summary(self) -> Dict[str, Any]:
        """Get a summary of the current configuration."""
        if not self.env_config:
            return {"error": "No configuration loaded"}
        
        return {
            "config_file": str(self.config_file_path) if self.config_file_path else "No file loaded",
            "environment_config": asdict(self.env_config),
            "base_config_paths": {
                "data_dir": str(base_config.paths.data_dir),
                "final_leaderboard": str(base_config.paths.final_leaderboard_parquet),
                "nation_rankings": str(base_config.paths.nation_rankings_parquet)
            }
        }
    
    def print_config_summary(self) -> None:
        """Print a formatted configuration summary."""
        summary = self.get_current_config_summary()
        
        if "error" in summary:
            self.logger.error(summary["error"])
            return
        
        self.logger.info("\n" + "="*60)
        self.logger.info("⚙️  CONFIGURATION SUMMARY")
        self.logger.info("="*60)
        self.logger.info(f"📄 Config file: {summary['config_file']}")
        
        env_config = summary['environment_config']
        self.logger.info(f"🎯 Min games threshold: {env_config['min_games_threshold']}")
        self.logger.info(f"⚡ Max workers: {env_config['max_workers']}")
        self.logger.info(f"💾 Cache duration: {env_config['cache_duration_hours']}h")
        self.logger.info(f"📊 Monitoring enabled: {env_config['enable_monitoring']}")
        self.logger.info(f"✅ Validation enabled: {env_config['enable_validation']}")
        self.logger.info(f"📝 Log level: {env_config['log_level']}")

# Global configuration manager
config_manager = ConfigurationManager()
