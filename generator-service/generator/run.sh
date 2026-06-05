#!/bin/bash

# Build and run the Docker container, passing env vars and mounting the output directory
docker build -t doc-gen .
docker run --rm --env-file .env -v "$(pwd)/output:/app/output" doc-gen
