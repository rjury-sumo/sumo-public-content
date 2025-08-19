# Config examples for sumo logic open telemetry agents.
Most of these are examples exported from common scenarios for agents using remote config templates as the source generator.

# Useful commands
| Use case  | Command  |
|---|---|
|  show merged config |  ```otelcol-sumo print-initial-config --feature-gates=otelcol.printInitialConfig --config ./opamp.d/0000B5E620F4853A.yaml --config ./opamp.d/sumologic-otCollector-tags.yaml --config sumologic.yaml```  |
|  get opamp files as a --config list for above |  ```ls opamp.d/*.yaml &#124; sed 's/^/ --config=/' &#124; tr '\n' ' '``` <br>For example ```--config=opamp.d/0000B5E620F4853A.yaml  --config=opamp.d/0000B5E620F4853F.yaml  --config=opamp.d/0000B5E620F48540.yaml  --config=opamp.d/sumologic-otCollector-tags.yaml```|
| start agent with * config dir | ```/usr/local/bin/otelcol-sumo --config /etc/otelcol-sumo/sumologic.yaml --config "glob:/etc/otelcol-sumo/conf.d/*.yaml"``` |
| view agent log | ```tail /var/log/otelcol-sumo/otelcol-sumo.log``` |

