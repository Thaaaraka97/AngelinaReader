import os
import datetime

class Config(object):
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'angilina'
    MODEL_PATH = ""
    DATA_ROOT = os.environ.get('DATA_ROOT') or 'static/data'
    PERMANENT_SESSION_LIFETIME = datetime.timedelta(minutes=60*24*365*2)