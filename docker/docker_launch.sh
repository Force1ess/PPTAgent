#!/bin/bash

if [ -z "$OPENAI_API_KEY" ]; then
  echo "Error: OPENAI_API_KEY is not set."
  echo "Please set the OPENAI_API_KEY environment variable using the command:"
  echo "docker run -e OPENAI_API_KEY='your-api-key'."
  exit 1
fi

export PYTHONPATH=/PPTAgent/src:$PYTHONPATH

# Sync the PPTAgent with Upstream
cd /PPTAgent
git pull

# Launch Backend Server
python3 pptagent_ui/backend.py &

# Launch Frontend Server
cd pptagent_ui
npm run serve
