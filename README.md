# Video Platform Systems Demo

A YouTube-style systems/data exercise focused on **event ingestion, watch analytics, recommendations, storage boundaries and scalable metadata** rather than frontend cloning.

## Scope

- video/channel/user metadata model
- append-only watch events
- event-time analytics
- watch-time and completion-rate features
- recommendation candidate tables
- Kafka/Spark-compatible event schema
- PostgreSQL/ClickHouse-style serving and analytics split

## Planned stack

FastAPI · PostgreSQL · Kafka · Spark Structured Streaming · ClickHouse · Redis · Docker Compose

The project is intentionally framed as a data/ML platform exercise.
