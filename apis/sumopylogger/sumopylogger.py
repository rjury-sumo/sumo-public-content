import logging
import requests 
import json
import datetime

class sumohandler(logging.Handler):

    def __init__(self, endpoint=None, category=None, host=None, fields=None, compressed=False):
        logging.Handler.__init__(self)
        if not endpoint:
                raise ValueError('endpoint cannot be null')
        self.endpoint = endpoint
        self.category = category
        self.host = host
        self.fields = fields
        self.headers = {"Content-type": "application/json"}
        self.compressed = compressed

    def emit(self, record):
        if self.compressed:
            self.headers["Content-Encoding"] = "gzip"
        if self.category:
            self.headers["X-Sumo-Category"] = self.category
        if self.host:
            self.headers["X-Sumo-Host"] = self.host
        if self.fields:
            self.headers["X-Sumo-Fields"] = self.fields

        # some code....
        return requests.post(self.endpoint, self.format(record), headers=self.headers).content

    def format(self, record):
            data = {
                    'timestamp': datetime.datetime.utcnow().strftime("%Y-%b-%dT%H:%M:%S+0000"),
                    'logger': record.name,
                    'level': record.levelname,
                    'text': record.msg
                    }

            return json.dumps(data)