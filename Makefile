.PHONY: up

up:
	docker compose up --build --wait
	@printf '\nWeb app:  http://localhost:3000\nAPI docs: http://localhost:8000/docs\n'
