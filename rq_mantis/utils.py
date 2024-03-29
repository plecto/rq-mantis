import os
import socket
from collections import namedtuple
from datetime import datetime
from operator import attrgetter


get_created_at = attrgetter('created_at')
QueueData = namedtuple('QueueData', ('queue', 'workers', 'running_jobs'))


def get_paginated_jobs(jobs, offset=0, per_page=1000):
    return sorted(jobs, key=get_created_at, reverse=True)[offset: offset + per_page]


def get_queues_workers_count(workers, queues):
    valid_queues = {queue for queue in queues if queue.name != "failed"}
    queues_workers = dict.fromkeys(list(valid_queues), 0)
    # Count all the workers on the queues
    for worker in workers:
        for queue in valid_queues.intersection(worker.queues):
            queues_workers[queue] += 1

    return queues_workers


def get_queues_data(workers, queues, registries_jobs_count):
    """
    Returns list with tuples of queue, workers_count and running_jobs_count
    [
        (queue, 3, 10),
        (queue2, 4, 7),
        (queue3, 0, 0)
    ]
    """
    queues_workers = get_queues_workers_count(workers=workers, queues=queues)
    return [
        QueueData(queue=queue, workers=workers_count, running_jobs=registries_jobs_count.get(queue.name, 0))
        for queue, workers_count in queues_workers.items()
    ]


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
            for queue, workers in get_queues_workers_count(self._workers, self._queues).items()
        )

    def scheduler_too_long_delay(self):
        """Scheduler not running"""

        short_name, _, _ = socket.gethostname().partition(".")
        key = "scheduler_last_run" + "." + short_name
        last_scheduler_timestamp = self._redis_conn.get(key)
        if last_scheduler_timestamp is None:
            return False
        if isinstance(last_scheduler_timestamp, bytes):
            last_scheduler_timestamp = last_scheduler_timestamp.decode('utf-8')

        d = datetime.strptime(last_scheduler_timestamp, "%Y-%m-%dT%H:%M:%S.%f")
        return (datetime.now() - d).total_seconds() > self.SCHEDULER_TIMEOUT
