# ============================================================
# ANDROMEDA — Comandos de desarrollo
# ============================================================

.PHONY: help start stop rebuild logs test clean models

help:
	@echo "Andromeda — comandos disponibles:"
	@echo "  make start     Levanta todos los contenedores"
	@echo "  make stop      Para todos los contenedores"
	@echo "  make rebuild   Reconstruye desde cero (tras cambios de codigo)"
	@echo "  make logs      Muestra los logs del backend"
	@echo "  make test      Ejecuta los tests"
	@echo "  make models    Descarga los modelos iniciales"
	@echo "  make clean     Limpia contenedores e imagenes"

start:
	docker-compose up -d
	@echo "Andromeda en http://localhost"

stop:
	docker-compose down

rebuild:
	docker-compose down
	docker rmi andromeda-frontend andromeda-backend 2>/dev/null || true
	docker-compose up -d --build
	@echo "Reconstruido. Andromeda en http://localhost"

logs:
	docker logs -f andromeda-backend

test:
	cd backend && python -m pytest ../tests/ -v

models:
	docker exec andromeda-ollama ollama pull phi3.5:3.8b
	docker exec andromeda-ollama ollama pull mistral:7b
	docker exec andromeda-ollama ollama pull qwen2.5-coder:7b
	@echo "Modelos descargados."

clean:
	docker-compose down -v
	docker rmi andromeda-frontend andromeda-backend 2>/dev/null || true
