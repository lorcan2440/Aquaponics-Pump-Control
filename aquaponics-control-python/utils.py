# built-ins
from datetime import datetime
import logging

# external modules
from rich.logging import RichHandler


class MicrosecondFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        if not datefmt:
            return super().formatTime(record, datefmt=datefmt)

        return datetime.fromtimestamp(record.created).astimezone().strftime(datefmt)


def get_logger(name: str = __name__) -> logging.Logger:
    """
    Return a configured logger. This function is idempotent - calling it
    multiple times with the same `name` will not add duplicate handlers.
    """

    logger = logging.getLogger(name)

    if logger.handlers:
        return logger  # avoid duplicate handlers if logger already configured

    formatter = MicrosecondFormatter(
        "%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S.%f",
    )

    file_handler = logging.FileHandler("debug.log")
    file_handler.setFormatter(formatter)

    console_handler = RichHandler(
        console=None,
        show_time=True,
        show_path=False,
        markup=True,
        rich_tracebacks=True,
        log_time_format=lambda dt: dt.strftime("%Y-%m-%d %H:%M:%S.%f"),
    )
    console_handler.setFormatter(logging.Formatter("%(message)s"))

    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger