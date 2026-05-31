.PHONY: build up down logs shell download-model

## Build the Docker image
build:
	docker compose build

## Start the bot in the background
up:
	docker compose up -d

## Stop the bot
down:
	docker compose down

## Tail container logs (Ctrl-C to exit)
logs:
	docker compose logs -f

## Open a shell inside the running container
shell:
	docker compose exec swingbot bash

## Pre-download Kronos model weights to ~/.cache/huggingface (run once before first 'make up')
download-model:
	pip install --quiet huggingface_hub
	python scripts/download_model.py
