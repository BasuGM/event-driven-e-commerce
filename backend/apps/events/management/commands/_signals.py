import signal
import threading


def stop_on_signals() -> threading.Event:
    """An Event set by SIGTERM (docker stop) or SIGINT (Ctrl+C): loops finish their current
    batch/message and exit instead of being killed mid-transaction."""
    stop = threading.Event()

    def handler(signum, frame):
        stop.set()

    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)
    return stop
