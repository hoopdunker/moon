import logging
import sys


def setup(debug: bool = False) -> None:
    level = logging.DEBUG if debug else logging.INFO
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(
        fmt="%(asctime)s [%(levelname)-5s] %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    ))
    logging.getLogger("moon").setLevel(level)
    logging.getLogger("moon").addHandler(handler)
    logging.getLogger("moon").propagate = False
