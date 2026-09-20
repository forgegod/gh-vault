.PHONY: verify records-check test test-python test-records

UV ?= uv
NODE ?= node

verify: records-check test

records-check:
	$(NODE) scripts/check-product-records.mjs

test: test-python test-records

test-python:
	$(UV) run --no-project --with pytest python -m pytest

test-records:
	$(NODE) --test "tests/records/*.test.mjs"
