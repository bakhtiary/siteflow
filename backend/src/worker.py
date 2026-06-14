from src.database import init_db
from src.queue import ensure_queue_schema
from src.worker_queue import app


def main() -> None:
    ensure_queue_schema()
    init_db()
    app.run_worker(queues=["clone"])


if __name__ == "__main__":
    main()
