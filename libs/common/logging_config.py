"""
Zentrales Logging-Modul für das LoraSense-System.
Stellt sicher, dass alle Services (Uplink, Dashboard, DB) einheitlich loggen.
"""

import logging
import os
from logging.handlers import RotatingFileHandler

def setup_logging(service_name, log_dir="/storage/logs", log_level=logging.INFO):
    """
    Richtet das Logging für einen Service ein.
    Ausgabe erfolgt sowohl auf die Konsole (stdout) als auch in eine rotierende Log-Datei.
    
    Args:
        service_name (str): Name des Services (wird für den Dateinamen verwendet).
        log_dir (str): Verzeichnis, in dem die Logs gespeichert werden.
        log_level (int): Das gewünschte Logging-Level (Default: INFO).
        
    Returns:
        logging.Logger: Ein vorkonfiguriertes Logger-Objekt.
    """
    # Sicherstellen, dass das Log-Verzeichnis existiert
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, f"{service_name}.log")
    
    # Logger-Instanz erstellen
    logger = logging.getLogger(service_name)
    logger.setLevel(log_level)
    
    # Vermeiden, dass Handler mehrfach hinzugefügt werden (bei Re-imports)
    if logger.handlers:
        return logger

    # Log-Format definieren (Zeitstempel - Name - Level - Nachricht)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Console Handler: Ausgabe im Terminal/Docker-Logs
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File Handler: Speicherung in Datei mit Rotation.
    # maxBytes=5MB, backupCount=3 (behält die letzten 3 Log-Dateien)
    file_handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=3)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger
