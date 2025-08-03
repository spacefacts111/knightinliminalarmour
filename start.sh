#!/bin/bash
echo "Installing Playwright..."
playwright install --with-deps
echo "Running bot..."
python3 main.py
