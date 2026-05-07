name: Daily AI-Generated VLSI Mock Test

on:
  schedule:
    - cron: '30 0 * * *'
  workflow_dispatch:

# IMPORTANT: Give write permission to push history file
permissions:
  contents: write

jobs:
  generate-and-send:
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Fetch all history for proper commit
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: pip install requests
      
      - name: Run AI mock test generator
        env:
          DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
          EMAIL_FROM: ${{ secrets.EMAIL_FROM }}
          EMAIL_PASSWORD: ${{ secrets.EMAIL_PASSWORD }}
          EMAIL_TO: ${{ secrets.EMAIL_TO }}
          SMTP_SERVER: ${{ secrets.SMTP_SERVER }}
          SMTP_PORT: ${{ secrets.SMTP_PORT }}
          GITHUB_ACTIONS: true
        run: python mock_test_dynamic.py
      
      - name: Push history file changes
        if: always()
        run: |
          git config --global user.email "github-actions[bot]@users.noreply.github.com"
          git config --global user.name "github-actions[bot]"
          git add question_history.json
          git commit -m "Update question history - $(date '+%Y-%m-%d')" || echo "No changes to commit"
          git push
