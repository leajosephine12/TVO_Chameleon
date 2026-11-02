"""Turn on the per-attempt timing log (it is silent unless a program calls this or sets up logging)."""
import logging


def enable_timing_logs(level: int = logging.INFO) -> None:
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(name)s %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("app.model").setLevel(level)
