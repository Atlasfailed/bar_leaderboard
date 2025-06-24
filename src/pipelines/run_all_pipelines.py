#!/usr/bin/env python3
"""
BAR Leaderboard Master Pipeline Runner
======================================

Orchestrates the execution of all data pipelines in the correct order.
This script runs:
1. Leaderboard calculation pipeline
2. Nation ranking pipeline  
3. Team analysis pipeline

Usage:
    python run_all_pipelines.py [options]
"""

import sys
import time
import argparse
import subprocess
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

from ..core.config import config
from ..core.utils import setup_logging, ProgressTracker

class MasterPipelineRunner:
    """Orchestrates the execution of all BAR leaderboard pipelines."""
    
    def __init__(self, min_games: int = 5, force_refresh: bool = False, 
                 parallel: bool = False, dry_run: bool = False):
        self.logger = setup_logging(self.__class__.__name__)
        self.min_games = min_games
        self.force_refresh = force_refresh
        self.parallel = parallel
        self.dry_run = dry_run
        self.start_time = time.time()
        
        # Define pipeline execution order and dependencies
        self.pipelines = [
            {
                'name': 'Leaderboard Calculation',
                'script': 'run_pipelinev2.py',
                'args': ['--min-games', str(min_games)],
                'output_files': [config.paths.final_leaderboard_parquet],
                'description': 'Calculates player leaderboards for all game types and regions'
            },
            {
                'name': 'Nation Rankings',
                'script': 'nation_ranking_pipeline.py',
                'args': ['--min-games', str(min_games)],
                'output_files': [config.paths.nation_rankings_parquet, config.paths.player_contributions_parquet],
                'description': 'Generates nation rankings and player contributions'
            },
            {
                'name': 'Team Analysis',
                'script': 'team_analysis.py',
                'args': ['--min-matches', '5', '--min-team-matches', '10'],
                'output_files': [config.paths.team_rosters_parquet],
                'description': 'Analyzes team rosters and player collaboration patterns'
            }
        ]
    
    def run_all_pipelines(self) -> bool:
        """Execute all pipelines in sequence."""
        self.logger.info("🚀 Starting BAR Leaderboard Master Pipeline")
        self.logger.info(f"Configuration: min_games={self.min_games}, force_refresh={self.force_refresh}")
        
        if self.dry_run:
            self.logger.info("🔍 DRY RUN MODE - No actual execution")
            self._show_execution_plan()
            return True
        
        # Check if refresh is needed
        if not self.force_refresh and self._check_if_refresh_needed():
            self.logger.info("📊 Data is up to date, skipping pipeline execution")
            return True
        
        # Execute pipelines
        results = []
        progress = ProgressTracker(len(self.pipelines), "Overall Progress")
        
        for i, pipeline in enumerate(self.pipelines, 1):
            self.logger.info(f"\n{'='*60}")
            self.logger.info(f"📈 Step {i}/{len(self.pipelines)}: {pipeline['name']}")
            self.logger.info(f"📝 {pipeline['description']}")
            self.logger.info(f"{'='*60}")
            
            start_time = time.time()
            success = self._run_pipeline(pipeline)
            duration = time.time() - start_time
            
            results.append({
                'name': pipeline['name'],
                'success': success,
                'duration': duration
            })
            
            if not success:
                self.logger.error(f"❌ Pipeline '{pipeline['name']}' failed!")
                self._show_summary(results)
                return False
            
            self.logger.info(f"✅ {pipeline['name']} completed in {duration:.1f}s")
            progress.update()
        
        # Show final summary
        self._show_summary(results)
        return True
    
    def _run_pipeline(self, pipeline: Dict[str, Any]) -> bool:
        """Execute a single pipeline."""
        # Calculate script path (go up to project root for entry points)
        project_root = Path(__file__).parent.parent.parent
        script_path = project_root / f"run_{pipeline['script'].split('_')[0]}.py"
        
        # Special handling for some scripts
        if pipeline['script'] == 'run_pipelinev2.py':
            script_path = project_root / 'run_leaderboard.py'
        elif pipeline['script'] == 'nation_ranking_pipeline.py':
            script_path = project_root / 'run_nation_rankings.py'
        elif pipeline['script'] == 'team_analysis.py':
            script_path = project_root / 'run_team_analysis.py'
        
        if not script_path.exists():
            self.logger.error(f"Script not found: {script_path}")
            return False
        
        # Build command
        cmd = [sys.executable, str(script_path)] + pipeline['args']
        self.logger.info(f"🔧 Executing: {' '.join(cmd)}")
        
        try:
            # Run the pipeline
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600  # 1 hour timeout
            )
            
            if result.returncode == 0:
                self.logger.info("📤 Pipeline output:")
                for line in result.stdout.strip().split('\n'):
                    if line.strip():
                        self.logger.info(f"  {line}")
                return True
            else:
                self.logger.error(f"❌ Pipeline failed with exit code {result.returncode}")
                self.logger.error("📤 Error output:")
                for line in result.stderr.strip().split('\n'):
                    if line.strip():
                        self.logger.error(f"  {line}")
                return False
                
        except subprocess.TimeoutExpired:
            self.logger.error("⏰ Pipeline timed out after 1 hour")
            return False
        except Exception as e:
            self.logger.error(f"💥 Unexpected error: {e}")
            return False
    
    def _check_if_refresh_needed(self) -> bool:
        """Check if any output files are missing or stale."""
        for pipeline in self.pipelines:
            for output_file in pipeline['output_files']:
                if not output_file.exists():
                    self.logger.info(f"🔄 Refresh needed: {output_file} is missing")
                    return True
                
                # Check if file is older than 24 hours
                file_age_hours = (time.time() - output_file.stat().st_mtime) / 3600
                if file_age_hours > 24:
                    self.logger.info(f"🔄 Refresh needed: {output_file} is {file_age_hours:.1f}h old")
                    return True
        
        return False
    
    def _show_execution_plan(self) -> None:
        """Show what would be executed in dry run mode."""
        self.logger.info("\n📋 EXECUTION PLAN:")
        for i, pipeline in enumerate(self.pipelines, 1):
            self.logger.info(f"  {i}. {pipeline['name']}")
            self.logger.info(f"     Script: {pipeline['script']}")
            self.logger.info(f"     Args: {' '.join(pipeline['args'])}")
            self.logger.info(f"     Outputs: {', '.join(str(f) for f in pipeline['output_files'])}")
            self.logger.info("")
    
    def _show_summary(self, results: List[Dict[str, Any]]) -> None:
        """Show execution summary."""
        total_duration = time.time() - self.start_time
        successful = sum(1 for r in results if r['success'])
        
        self.logger.info(f"\n{'='*60}")
        self.logger.info("📊 EXECUTION SUMMARY")
        self.logger.info(f"{'='*60}")
        self.logger.info(f"📈 Total pipelines: {len(results)}")
        self.logger.info(f"✅ Successful: {successful}")
        self.logger.info(f"❌ Failed: {len(results) - successful}")
        self.logger.info(f"⏱️  Total time: {total_duration:.1f}s")
        self.logger.info("")
        
        for result in results:
            status = "✅" if result['success'] else "❌"
            self.logger.info(f"{status} {result['name']}: {result['duration']:.1f}s")
        
        if all(r['success'] for r in results):
            self.logger.info("\n🎉 All pipelines completed successfully!")
        else:
            self.logger.error("\n💥 Some pipelines failed. Check logs above for details.")

def main():
    """Main execution entry point."""
    parser = argparse.ArgumentParser(
        description="BAR Leaderboard Master Pipeline Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        '--min-games',
        type=int,
        default=5,
        help='Minimum games required for leaderboard inclusion (default: 5)'
    )
    
    parser.add_argument(
        '--force-refresh',
        action='store_true',
        help='Force refresh even if data appears up to date'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show execution plan without running pipelines'
    )
    
    parser.add_argument(
        '--parallel',
        action='store_true',
        help='Run independent pipelines in parallel (experimental)'
    )
    
    args = parser.parse_args()
    
    # Create and run the master pipeline
    runner = MasterPipelineRunner(
        min_games=args.min_games,
        force_refresh=args.force_refresh,
        parallel=args.parallel,
        dry_run=args.dry_run
    )
    
    try:
        success = runner.run_all_pipelines()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⚠️  Pipeline execution interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
