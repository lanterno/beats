build:
	docker-compose build
up:
	docker-compose up --remove-orphans

shell:
	docker-compose run --rm api bash
