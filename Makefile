# Pipeline A — convenience targets (requires Python 3.11+, Node/npm for UI).
# On Windows without `make`, use: npm run dev | npm test | npm run demo

.PHONY: dev test demo lint loadtest

dev:
	npm run dev

test:
	npm run test

demo:
	npm run demo

lint:
	npm run lint

# Requires: LOCUST_HOST, TEST_API_KEY, TEST_PIPELINE_ID (and `pip install locust` or uv sync)
loadtest:
	locust -f arctis/loadtests/locustfile.py --headless -u 10 -r 2 -t 30s
