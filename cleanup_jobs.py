#!/usr/bin/env python3
"""
Cleanup script for stalled processing jobs.
This script can be run periodically via cron to clean up jobs that have been
pending for more than 10 minutes.

Usage:
    python cleanup_jobs.py

Cron example (run every 15 minutes):
    */15 * * * * /path/to/venv/bin/python /path/to/cleanup_jobs.py >> /var/log/pdf_compressor_cleanup.log 2>&1
"""

import sys
import os
from datetime import datetime

# Add the current directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from models.processing_job import ProcessingJob

def main():
    """Main cleanup function."""
    print(f"[{datetime.now().isoformat()}] Starting job cleanup...")
    
    app = create_app()
    
    with app.app_context():
        try:
            # Clean up stalled jobs
            cleaned_count = ProcessingJob.cleanup_stalled_jobs()
            
            if cleaned_count > 0:
                print(f"[{datetime.now().isoformat()}] Cleaned up {cleaned_count} stalled job(s)")
            else:
                print(f"[{datetime.now().isoformat()}] No stalled jobs found")
                
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] Error during cleanup: {e}")
            sys.exit(1)
    
    print(f"[{datetime.now().isoformat()}] Cleanup completed successfully")

if __name__ == "__main__":
    main()
