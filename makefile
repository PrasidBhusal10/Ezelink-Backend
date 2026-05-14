up:
	docker compose up --build -d
start:
	docker compose up -d
down:
	docker compose down
reset:
	docker compose down -v
rebuild:
	docker compose build --no-cache
	docker compose up -d
logs:
	docker compose logs -f
logs-api:
	docker compose logs -f api
logs-worker:
	docker compose logs -f worker
logs-kafka:
	docker compose logs -f kafka
ps:
	docker compose ps
stats:
	docker stats --no-stream
shell:
	docker compose exec api bash
db-shell:
	docker compose exec db psql -U app -d shortener
redis-shell:
	docker compose exec redis redis-cli
kafka-topics:
	docker compose exec kafka kafka-topics --bootstrap-server localhost:9092 --list

kafka-watch:
	docker compose exec kafka kafka-console-consumer \
		--bootstrap-server localhost:9092 \
		--topic click-events \
		--from-beginning

test:
	python test_phase4.py

.PHONY: up start down reset rebuild logs logs-api logs-worker logs-kafka ps stats shell db-shell redis-shell kafka-topics kafka-watch test