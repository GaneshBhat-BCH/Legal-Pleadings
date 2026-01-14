import csv
import os
from datetime import datetime
from pathlib import Path

LOG_PREFIX = "activity_log_"
RETENTION_DAYS = 15

def cleanup_old_logs():
    """
    Deletes log files older than RETENTION_DAYS (15 days).
    """
    try:
        today = datetime.now().date()
        # Iterate over all files in current directory matching pattern
        for file in Path(".").glob(f"{LOG_PREFIX}*.csv"):
            try:
                # Extract date string from filename "activity_log_YYYY-MM-DD.csv"
                date_str = file.stem.replace(LOG_PREFIX, "")
                file_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                
                days_diff = (today - file_date).days
                
                if days_diff > RETENTION_DAYS:
                    os.remove(file)
                    print(f"Deleted old log file: {file} ({days_diff} days old)")
            except ValueError:
                continue # Skip files that don't match date format
    except Exception as e:
        print(f"Log cleanup failed: {e}")

def log_event(module: str, comment: str, status: str = "INFO"):
    """
    Logs an event to activity_log_YYYY-MM-DD.csv.
    Format: [Time, Module run, Comment, Status]
    Auto-deletes files older than 15 days.
    """
    # 1. Determine Today's Log File
    current_date = datetime.now().strftime("%Y-%m-%d")
    log_file = Path(f"{LOG_PREFIX}{current_date}.csv")
    
    file_exists = log_file.exists()
    
    try:
        # 2. Append to Log
        with open(log_file, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            
            # Write Header if new file
            if not file_exists:
                writer.writerow(["Time", "Module run", "Comment", "Status"])
            
            # Write Row
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            writer.writerow([current_time, module, comment, status])
            
        # 3. Trigger Cleanup (Simple implementation: run every write)
        # Verify overhead is negligible for <100 files
        cleanup_old_logs()
            
    except Exception as e:
        print(f"Logging Failed: {e}")
