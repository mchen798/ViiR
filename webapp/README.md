# ViiR Web Application

This directory contains a demonstration web application using FastAPI, Celery and a React dashboard.
It showcases a simple bioinformatics SaaS frontend with navigation, task wizard,
history table and progress pages.

## Requirements

- Docker and Docker Compose

## Services

- **backend**: FastAPI API server
- **worker**: Celery worker processing background tasks
- **frontend**: React application using Ant Design and Plotly
- **redis**: Message broker for Celery

## Quick Start

From this `webapp` directory, run:

```bash
docker-compose up --build
```

Then open `http://localhost:3000` to view the frontend.

The frontend provides a dashboard listing submitted tasks and a wizard for creating new analyses. Plotly is used for interactive charts.

## Project Structure

```
webapp/
  backend/      # FastAPI application and Celery tasks
  frontend/     # React application
  docker-compose.yml
```
