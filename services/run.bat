@echo off
docker compose -f docker-compose.yml -f docker-compose.gpu.yml  -f docker-compose.local.yml -f ../data/docker-compose.mounts.yml up -d --build noted