"""Single control owner; retain the existing eight HTTP threads."""
import signal

workers = 1
threads = 8
preload_app = False
graceful_timeout = 20


def on_starting(server):
    if server.cfg.workers != 1 or server.cfg.preload_app:
        raise RuntimeError('HC requires one non-preloaded control worker')


def post_worker_init(worker):
    previous = signal.getsignal(signal.SIGTERM)
    def terminate(signum, frame):
        from app import shutdown_backend
        shutdown_backend(0)
        if callable(previous):
            previous(signum, frame)
    signal.signal(signal.SIGTERM, terminate)


def worker_exit(server, worker):
    from app import shutdown_backend
    shutdown_backend(8)
