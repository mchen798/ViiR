# ViiR Web Application

This directory contains a small demonstration web application using FastAPI and React.

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

The frontend fetches sample data from the backend `/data` endpoint and displays it using Plotly. Clicking **Run Background Task** triggers a Celery job via the `/process` endpoint.

## Project Structure

```
webapp/
  backend/      # FastAPI application and Celery tasks
  frontend/     # React application
  docker-compose.yml
```
