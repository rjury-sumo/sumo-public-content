# Custom Nginx Logs

A custom verson of the nginx logs app but for logs only.

Requres an FER. This may vary based on your nginx logs. Expects field names such as sc_status, cs_uri_stem etc.
IP lookup panels use a custom formula to pick the first valid ip in this order:
1. x_forwarded_for
2. c_ip