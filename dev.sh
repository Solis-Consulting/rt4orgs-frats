#!/bin/bash
# Development server startup script
# Run this from anywhere: ./dev.sh

cd "$(dirname "$0")"
uvicorn main:app --reload --reload-dir .

