# Risk files

Copies of the risk assessment engine's risk files (its `config/risks/*.yaml`), one file per risk, unchanged.
TRUST reads `domain`, `category`, `name` and `description` to show on the Metric dictionary under
"Risk it watches". Everything else in the file is ignored here.

A metric links to a risk in `config/metrics.json`: `card.risks` lists file names without `.yaml`, for example
`["external-data-breach-tool-use"]`. To update a risk, replace its file with the engine's newer copy and deploy.
The tests fail if a metric names a risk file that isn't here.
