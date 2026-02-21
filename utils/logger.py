import logging
import colorlog
import sys

def setup_logger(name="XTVredirect", level=logging.INFO):
    """
    Sets up a colored logger suitable for Railway logs.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # If handlers already exist, don't add more
    if logger.handlers:
        return logger

    handler = logging.StreamHandler(sys.stdout)

    # Custom color scheme for Railway logs
    formatter = colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        reset=True,
        log_colors={
            'DEBUG':    'cyan',
            'INFO':     'green',
            'WARNING':  'yellow',
            'ERROR':    'red',
            'CRITICAL': 'red,bg_white',
        },
        secondary_log_colors={},
        style='%'
    )

    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger
