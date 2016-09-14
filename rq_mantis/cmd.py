import click

from app import app


@click.command()
@click.option('--redis-url', default='redis://localhost:6379', help='Redis url eg. redis://localhost:6379')
@click.option('--debug', default=False, help='Debug mode')
@click.option('--host', default='127.0.0.1', help='Host')
@click.option('--port', default=5000, help='Port')
def run(redis_url, debug, host, port):
    app.config['REDIS_URL'] = redis_url
    app.run(host, port, debug)


if __name__ == '__main__':
    run()
