import rq
import socket
from flask import Flask
from flask import current_app
from flask import redirect
from flask import render_template
from flask import request
from flask import url_for
from redis import from_url, ConnectionError
from rq import get_failed_queue
from rq.job import Job
from werkzeug.exceptions import ServiceUnavailable

from rq_mantis.utils import WorkersChecker, get_queues_data, get_paginated_jobs
from flask_paginate import Pagination, get_page_args

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
    try:
        workers = rq.Worker.all()
        queues = rq.Queue.all()
    except ConnectionError:
        raise ServiceUnavailable("Cannot establish connection to redis")

    machine_workers = [
        worker
        for worker in workers
        if worker.name.split('.')[0] == socket.gethostname().partition(".")[0]
    ]

    checker = WorkersChecker(current_app.redis_conn, machine_workers, queues)

    if checker.scheduler_too_long_delay():
        raise ServiceUnavailable("Scheduler not running")
    elif checker.no_active_workers():
        raise ServiceUnavailable("No workers are running")
    elif checker.process_is_missing():
        raise ServiceUnavailable("Some worker processes are missing")
    elif checker.some_workers_expired():
        raise ServiceUnavailable("Some worker processes have expired TTL")
    elif checker.queues_without_workers():
        raise ServiceUnavailable("There are queues without active workers")
    else:
        return "It's working"


@app.route("/")
def index():
    workers = rq.Worker.all()
    queues = [q for q in rq.Queue.all() if q.name != 'failed']
    registries_jobs_count = {q.name: rq.registry.StartedJobRegistry(q.name).count for q in queues}

    queues_data = get_queues_data(workers, queues, registries_jobs_count)

    return render_template('index.html', queues=queues_data, failed_queue=get_failed_queue())


def get_queue_by_name(name):
    queues = rq.Queue.all()
    queue = None
    for q in queues:
        if q.name == name:
            queue = q
            break

    return queue


@app.route("/queue/failed/requeue-all", methods=["POST"])
def queue_requeue_all():

    if 'confirm' not in request.form:
        return render_confirm()

    fq = get_failed_queue()
    for job_id in fq.job_ids:
        requeue_job(job_id)
    return redirect(url_for('index', name='failed', _external=True))


@app.route("/queue/<name>/clear", methods=["POST"])
def queue_empty(name):

    if 'confirm' not in request.form:
        return render_confirm()

    queue = get_queue_by_name(name)
    queue.empty()
    return redirect(url_for('queue_detail', name=name, _external=True))


@app.route("/queue/<name>")
def queue_detail(name):
    page, per_page, offset = get_page_args(
        page_parameter='page',
        per_page_parameter='per_page'
    )
    queue = get_queue_by_name(name)
    jobs = get_paginated_jobs(queue.jobs, offset=offset, per_page=per_page)
    pagination = Pagination(page=page, total=queue.count, record_name='jobs')
    running_jobs = {
        Job.fetch(job_id)
        for job_id in rq.registry.StartedJobRegistry(name).get_job_ids()
    }

    return render_template(
        'queue.html',
        queue_name=queue.name,
        jobs=jobs,
        running_jobs=running_jobs,
        pagination=pagination,
    )


@app.route("/queue/failed/job/<uuid>/requeue", methods=["POST"])
def requeue_job(uuid):

    if 'confirm' not in request.form:
        return render_confirm()

    rq.requeue_job(uuid)
    return redirect(url_for('index', name='failed', _external=True))


@app.route("/queue/failed/job/<uuid>/clear", methods=["POST"])
def clear_failed_job(uuid):

    if 'confirm' not in request.form:
        return render_confirm()

    get_failed_queue().remove(uuid)
    return redirect(url_for('index', name='failed', _external=True))


@app.route("/queue/<name>/job/<uuid>/cancel")
def cancel(name, uuid):
    rq.cancel_job(uuid)
    return redirect(url_for('queue_detail', name=name, _external=True))


def render_confirm():
    return render_template('confirm.html')