#!/bin/bash

# Build the Docker image using the Dockerfile in the current directory
docker build -t docling-pdf .

# Run the container, mounting the current directory to /app inside the container
docker run --rm \
  -v $(pwd):/app \
  docling-pdf
