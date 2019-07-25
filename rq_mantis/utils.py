import os
import socket
from datetime import datetime
from collections import defaultdict


def get_queues_workers_count(workers, queues):
    """
    Returns dict with queue (actual objects - as they are hashable) and workers count:
    {
      queue_object: 4,
      queue_object_2: 0,
      queue_object_3: 1
    }
    """
    valid_queues = {queue for queue in queues if queue.name != "failed"}
    queues_workers = dict.fromkeys(list(valid_queues), 0)

    # Count all the workers on the queues
    for worker in workers:
        for queue in valid_queues.intersection(worker.queues):
            queues_workers[queue] += 1

    return queues_workers


class WorkersChecker(object):
    SCHEDULER_TIMEOUT = 15

    def __init__(self, redis_conn, workers, queues):
        self._redis_conn = redis_conn
        self._workers = workers
        self._queues = queues

    @property
    def _active_workers(self):
        return [worker for worker in self._workers if self._redis_conn.ttl(worker.key) > 0]

    def process_is_missing(self):
        """Not all workers are running"""
        try:
            for worker in self._workers:
                worker_pid = int(worker.name.split(".")[1])
                os.kill(worker_pid, 0)  # checks if process exists only
        except OSError:
            return True
        else:
            return False

    def some_workers_expired(self):
        """Not all workers are running"""
        return len(self._workers) != len(self._active_workers)

    def no_active_workers(self):
        """No workers are running"""
        return len(self._active_workers) == 0

    def queues_without_workers(self):
        """There are queues without active workers"""
        return any(
            queue.count > 0 and workers == 0
            for queue, workers in get_queues_workers_count(self._workers, self._queues)
        )

    def scheduler_too_long_delay(self):
        """Scheduler not running"""

        short_name, _, _ = socket.gethostname().partition(".")
        key = "scheduler_last_run" + "." + short_name
        last_scheduler_timestamp = self._redis_conn.get(key)
        if last_scheduler_timestamp is None:
            return False

        d = datetime.strptime(last_scheduler_timestamp, "%Y-%m-%dT%H:%M:%S.%f")
        return (datetime.now() - d).total_seconds() > self.SCHEDULER_TIMEOUT
