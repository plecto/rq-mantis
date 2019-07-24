import rq
from flask import Flask
from flask import current_app
from flask import redirect
from flask import render_template
from flask import request
from flask import url_for
from redis import from_url, ConnectionError
from rq import get_failed_queue
from werkzeug.exceptions import ServiceUnavailable

from rq_mantis.utils import WorkersChecker, get_queues_workers_count

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

    checker = WorkersChecker(current_app.redis_conn, workers, queues)

    if checker.scheduler_too_long_delay():
        raise ServiceUnavailable("Scheduler not running")
    elif checker.no_active_workers():
        raise ServiceUnavailable("No workers are running")
    elif checker.process_is_missing() or checker.some_workers_expired():
        raise ServiceUnavailable("Not all workers are running")
    elif checker.queues_without_workers():
        raise ServiceUnavailable("There are queues without active workers")
    else:
        return "It's working"


@app.route("/")
def index():
    workers = rq.Worker.all()
    queues = rq.Queue.all()

    queues_workers = get_queues_workers_count(workers, queues)

    return render_template('index.html', queues=queues_workers, failed_queue=get_failed_queue())


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
    return redirect(url_for('index', name='failed'))


@app.route("/queue/<name>/clear", methods=["POST"])
def queue_empty(name):

    if 'confirm' not in request.form:
        return render_confirm()

    queue = get_queue_by_name(name)
    queue.empty()
    return redirect(url_for('queue_detail', name=name))


@app.route("/queue/<name>")
def queue_detail(name):
    queue = get_queue_by_name(name)

    return render_template('queue.html', queue=queue)


@app.route("/queue/failed/job/<uuid>/requeue", methods=["POST"])
def requeue_job(uuid):

    if 'confirm' not in request.form:
        return render_confirm()

    rq.requeue_job(uuid)
    return redirect(url_for('index', name='failed'))


@app.route("/queue/failed/job/<uuid>/clear", methods=["POST"])
def clear_failed_job(uuid):

    if 'confirm' not in request.form:
        return render_confirm()

    get_failed_queue().remove(uuid)
    return redirect(url_for('index', name='failed'))


@app.route("/queue/<name>/job/<uuid>/cancel")
def cancel(name, uuid):
    rq.cancel_job(uuid)
    return redirect(url_for('queue_detail', name=name))


def render_confirm():
    return render_template('confirm.html')