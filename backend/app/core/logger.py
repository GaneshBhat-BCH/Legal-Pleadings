import csv
import logging
from datetime import datetime
from pathlib import Path

# Setup basic Python logger for console
logger = logging.getLogger("legal_pleadings")
logger.setLevel(logging.INFO)
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

class ActivityLogger:
    def __init__(self, log_dir="logs"):
        """Initialize the logger, creating the log directory if it doesn't exist."""
        # Calculate absolute path relative to exactly this file's position inside backend/app/core/
        self.base_dir = Path(__file__).parent.parent.parent.parent
        self.log_dir = self.base_dir / log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
    def _get_log_filename(self) -> str:
        """Returns the current day's log filename."""
        today = datetime.now().strftime("%Y-%m-%d")
        return str(self.log_dir / f"activity_log_{today}.csv")

    def _ensure_headers(self, file_path: str):
        """Ensures the CSV has headers if the file is new."""
        path = Path(file_path)
        if not path.exists() or path.stat().st_size == 0:
            with open(path, mode='w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(["Timestamp", "Endpoint", "Status", "Target", "Details"])

    def log_event(self, endpoint: str, status: str, target: str, details: str = ""):
        """
        Logs an event to the daily CSV file.
        
        :param endpoint: Processing endpoint (e.g., 'Extraction' or 'Generation')
        :param status: 'START', 'SUCCESS', 'ERROR'
        :param target: File path, party name, or ID
        :param details: Optional JSON or exception string
        """
        try:
            filename = self._get_log_filename()
            self._ensure_headers(filename)
            
            # Format safely
            timestamp = datetime.now().isoformat()
            
            with open(filename, mode='a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([timestamp, endpoint, status, target, details])
                
            # Also log to console
            logger.info(f"[{endpoint}] {status} - {target}")
            if details and status == "ERROR":
                logger.error(f"Details: {details}")
                
        except Exception as e:
            # Fallback to standard console logger if file op fails
            logger.error(f"Failed to write to activity CSV log: {e}")

# Global instance
activity_logger = ActivityLogger()
