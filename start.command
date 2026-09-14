#!/bin/zsh
# Double-click to start Aleena's Recipe Box on this Mac and your Wi-Fi.
cd "$(dirname "$0")"
export PATH="/opt/homebrew/bin:$HOME/.local/bin:$PATH"
if [ ! -f .env ]; then
  echo "No .env file yet. Copy .env.example to .env and paste your Anthropic key,"
  echo "or the Cook with tab will stay disabled. Starting anyway..."
fi
exec uv run server.py
