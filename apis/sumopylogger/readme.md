# sumopylogger
A simple example implementation of a python logger to stream data to a sumo HTTPS endpoint.
Note using DEBUG level with this logger unless you add filtering for the logger to exclude requests is **not recommended** as it can create an loop with DEBUG:urllib3.connectionpool:Starting...

# how to use
set env var SUMO_URL to your https source endpoint
optionally set SUMO_CATEGORY,SUMO_HOST, SUMO_FIELDS
run demo.py

![screenshot](./example-log.png?raw=true "screenshot")

The log events will appear in sumo in JSON format similar to below:
```
{"timestamp": "2019-Jul-12T01:19:47+0000", "logger": "root", "level": "INFO", "text": "Test info 2"}

{"timestamp": "2019-Jul-12T01:19:48+0000", "logger": "root", "level": "WARNING", "text": "Test warning 3"}

{"timestamp": "2019-Jul-12T01:19:49+0000", "logger": "root", "level": "ERROR", "text": "Test error 4"}

{"timestamp": "2019-Jul-12T01:19:50+0000", "logger": "root", "level": "CRITICAL", "text": "Test critical 5"}

{"timestamp": "2019-Jul-12T01:19:51+0000", "logger": "root", "level": "INFO", "text": "anything you log here will be converted to json by the logger and turn up in the text field"}

{"timestamp": "2019-Jul-12T01:19:51+0000", "logger": "root", "level": "INFO", "text": {"this": "will look like a json dict", "in": "sumo UI"}}

{"timestamp": "2019-Jul-12T01:19:52+0000", "logger": "root", "level": "INFO", "text": ["this", "will look like a json", "list"]}
```