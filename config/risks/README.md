# Risk files

Copies of the risk assessment engine's risk files (its `config/risks/*.yaml`), unchanged. Each file is one domain
(e.g. `air.cyber.yaml`) holding several risks, each with an ID like `air.cyber.01` (owner, 9 Nov 2026). TRUST reads
each risk's `domain`, `category`, `name` and `description` to show on the Metric dictionary under "Risk it watches".
Everything else in the file is ignored here.

A metric links to risks in `config/metrics.json` by **risk ID**: `card.risks`, for example `["air.cyber.01"]`.
The same IDs are in the risk assessment file, so a metric card can say which families the risk is Elevated for.
To update risks, replace the files with the engine's newer copies and deploy. The tests fail if a metric names a
risk ID that isn't in these files.

A file may hold risks keyed by ID (`air.cyber.01:` or `'01':` under `air.cyber.yaml`), as a list (each with an
`id`, else numbered `.01`, `.02` in order), or under a `risks:` key. A file holding a single risk is keyed by its
own `id`, else by the file name.
