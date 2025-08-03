#!/bin/bash
echo "📦 Installing Playwright..."
playwright install --with-deps
echo "🚀 Starting bot..."
python3 main.py
