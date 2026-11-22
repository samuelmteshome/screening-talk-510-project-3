TOPIC ?= prostate
PY ?= python

.PHONY: data download clean upload ingest test

# Full data step for one topic: download -> raw snapshot -> clean -> upload + record hash
data: download clean upload

download:
	$(PY) -m src.data.download --topic $(TOPIC) --snapshot

clean:
	$(PY) -m src.data.clean --topic $(TOPIC)

upload:
	$(PY) -m src.data.upload --topic $(TOPIC) --write-hash

ingest:
	$(PY) -m src.data.ingest --topic $(TOPIC)

test:
	$(PY) -m pytest -q tests
