# Setup logging
import logging
import sys
import uuid

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def get_logger(name: str) -> logging.Logger:
    """Get a logger with the specified name."""
   
    logging_group = uuid.uuid4() 
    return logging.LoggerAdapter(
        logging.getLogger(name),
        extra={"group": logging_group},
    ).logger
