import os
import urlparse

REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379')

try:
    from local_settings import *
except ImportError:
    pass
