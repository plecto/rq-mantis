import os


def process_exists(pid):
    try:
        os.kill(pid, 0)  # this checks if the process exists or not
    except OSError:
        return False
    return True
