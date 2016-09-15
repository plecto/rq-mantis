import os
import socket

import rq
from flask import Flask
from flask import current_app
from flask import redirect
from flask import render_template
from flask import url_for
from redis import from_url
from rq import get_failed_queue
from werkzeug.exceptions import ServiceUnavailable

app = Flask(__name__)


@app.before_first_request
def setup_rq_connection():
    redis_url = current_app.config.get('REDIS_URL')
    current_app.redis_conn = from_url(redis_url)


@app.before_request
def push_rq_connection():
    rq.push_connection(current_app.redis_conn)


@app.teardown_request
def pop_rq_connection(exception=None):
    rq.pop_connection()


@app.route("/__ht/")
def health_check():
    worker_count = 0
    hostname = socket.gethostname()
    shortname, _, _ = hostname.partition('.')
    for worker in rq.Worker.all():
        # only run health-check against own workers
        if worker.name.split('.')[0] != shortname:
            continue

        try:
            os.kill(int(worker.name.split('.')[1]), 0)
        except OSError:
            continue

        if current_app.redis_conn.ttl(worker.key) > 0:
            worker_count += 1

    if worker_count <= 0:
        # no workers are running
        raise ServiceUnavailable("No workers are running")
    return "It's working"


@app.route("/")
def index():
    workers = rq.Worker.all()
    queues = rq.Queue.all()

    queues_dict = {}
    for q in queues:
        queues_dict[q.name] = {'workers': 0, 'queue': q}

    if 'failed' in queues_dict:
        del queues_dict['failed']

    # Failed queue
    fq = get_failed_queue()

    # Count all the workers on the queues
    for w in workers:
        for q in w.queues:
            if q.name in queues_dict:
                queues_dict[q.name]['workers'] += 1

    return render_template('index.html', queues=queues_dict, failed_queue=fq)


def get_queue_by_name(name):
    queues = rq.Queue.all()
    queue = None
    for q in queues:
        if q.name == name:
            queue = q
            break

    return queue


@app.route("/queue/failed/requeue-all")
def queue_requeue_all():
    fq = get_failed_queue()
    for job_id in fq.job_ids:
        requeue_job(job_id)
    return redirect(url_for('queue_detail', name='failed'))


@app.route("/queue/<name>/clear")
def queue_empty(name):
    queue = get_queue_by_name(name)
    queue.empty()
    return redirect(url_for('queue_detail', name=name))


@app.route("/queue/<name>")
def queue_detail(name):
    queue = get_queue_by_name(name)

    return render_template('queue.html', queue=queue)


@app.route("/queue/failed/job/<uuid>/requeue")
def requeue_job(uuid):
    rq.requeue_job(uuid)
    return redirect(url_for('index'))


@app.route("/queue/<name>/job/<uuid>/cancel")
def cancel(name, uuid):
    rq.cancel_job(uuid)
    return redirect(url_for('index'))
