import sys
import os
import logging
import logging.handlers
from sumopylogger import sumohandler

# how to add a custom sumo logger to your logging config
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger()

logging.handlers.sumo = sumohandler

if os.environ.get('SUMO_URL') is not None:
    endpoint=os.environ['SUMO_URL']

if endpoint is None:
    logger.fatal ("you must supply a sumo endpoint via env var SUMO_URl")
    exit(1)

if os.environ.get('SUMO_CATEGORY') is not None:
    category=os.environ['SUMO_CATEGORY']
else:
    category="test/sumopylogger/json"

if os.environ.get('SUMO_HOST') is not None:
    host=os.environ['SUMO_HOST']
else:
    host=os.uname()[1]

if os.environ.get('SUMO_FIELDS') is not None:
    fields=os.environ['SUMO_FIELDS']
else:
    fields='owner=none,service=none,application=none'

sumo_logger = logging.handlers.sumo(endpoint = endpoint,
                                    category=category,
                                    host=host,
                                    fields=fields)
logger.addHandler(sumo_logger)
logger.setLevel('INFO')

# here are some examples of logging to sumo
logger.debug('Test debug 1')
logger.info('Test info 2')
logger.warning('Test warning 3')
logger.error('Test error 4')
logger.critical('Test critical 5')
logger.info('anything you log here will be converted to json by the logger and turn up in the text field')
logger.info({ 'this': 'will look like a json dict', 'in': 'sumo UI'})
logger.info(['this','will look like a json','list'])

