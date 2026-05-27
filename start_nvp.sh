#!/bin/bash
# NVP Linux Orchestrator

# Find the exact directory this script is living in
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Run the master orchestrator detached from the terminal
nohup python3 "$DIR/nvp_launcher.py" > /dev/null 2>&1 &

echo "NVP Backend Services Started in the background."