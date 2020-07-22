build:
	docker-compose build
up:
	docker-compose up --remove-orphans

shell:
	docker-compose run --rm api bash

ops:  # use this to install packages, and run system operations
	docker-compose -f compose-ops.yml run --rm api bash
test:
	docker-compose run --rm api pytest