name: Test Earnings Market Reaction V4

on:
  workflow_dispatch:

  push:
    paths:
      - "earnings_breadth_v2.py"
      - "earnings_market_reaction_v4.py"
      - "requirements.txt"
      - ".github/workflows/test_earning_reaction_v4.yml"

jobs:

  earnings-market-reaction-v4:

    runs-on: ubuntu-latest

    steps:

      # ==========================================================
      # Checkout
      # ==========================================================

      - name: Checkout repository
        uses: actions/checkout@v4

      # ==========================================================
      # Python
      # ==========================================================

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      # ==========================================================
      # Debug repository
      # ==========================================================

      - name: Repository Debug
        run: |
          echo "=========================================="
          echo "WORKSPACE"
          echo "=========================================="
          pwd

          echo ""
          echo "=========================================="
          echo "GIT BRANCH"
          echo "=========================================="
          git branch --show-current

          echo ""
          echo "=========================================="
          echo "GIT COMMIT"
          echo "=========================================="
          git log -1 --oneline

          echo ""
          echo "=========================================="
          echo "FILES"
          echo "=========================================="
          find . -maxdepth 1 -type f

      # ==========================================================
      # Check V2
      # ==========================================================

      - name: Check V2 Script
        run: |
          echo "=========================================="
          echo "CHECK V2"
          echo "=========================================="

          if [ -f "earnings_breadth_v2.py" ]; then
              echo "V2 FOUND"
          else
              echo "ERROR: earnings_breadth_v2.py NOT FOUND"
              exit 1
          fi

      # ==========================================================
      # Check V4
      # ==========================================================

      - name: Check V4 Script
        run: |
          echo "=========================================="
          echo "CHECK V4"
          echo "=========================================="

          ls -lh

          if [ -f "earnings_market_reaction_v4.py" ]; then
              echo "V4 FOUND"
          else
              echo "ERROR: earnings_market_reaction_v4.py NOT FOUND"
              exit 1
          fi

      # ==========================================================
      # Install dependencies
      # ==========================================================

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip

          if [ -f "requirements.txt" ]; then
              pip install -r requirements.txt
          fi

          pip install pandas
          pip install requests
          pip install yfinance
          pip install numpy

      # ==========================================================
      # Run V2
      # ==========================================================

      - name: Run Earnings Breadth V2
        env:
          ALPHAVANTAGE_API_KEY: ${{ secrets.ALPHAVANTAGE_API_KEY }}
        run: |
          echo "=========================================="
          echo "RUNNING V2"
          echo "=========================================="

          python earnings_breadth_v2.py

      # ==========================================================
      # Check V2 Output
      # ==========================================================

      - name: Verify V2 Output
        run: |
          echo "=========================================="
          echo "CHECK V2 OUTPUT"
          echo "=========================================="

          if [ -f "earnings_breadth_events_v2.csv" ]; then
              echo "CSV FOUND"
              ls -lh earnings_breadth_events_v2.csv
          else
              echo "ERROR: earnings_breadth_events_v2.csv NOT FOUND"
              exit 1
          fi

      # ==========================================================
      # Run V4
      # ==========================================================

      - name: Run Earnings Market Reaction V4
        run: |
          echo "=========================================="
          echo "RUNNING V4"
          echo "=========================================="

          python earnings_market_reaction_v4.py

      # ==========================================================
      # Check outputs
      # ==========================================================

      - name: Verify V4 Outputs
        run: |
          echo "=========================================="
          echo "CHECK OUTPUTS"
          echo "=========================================="

          ls -lh *.csv || true

      # ==========================================================
      # Upload results
      # ==========================================================

      - name: Upload CSV Files
        uses: actions/upload-artifact@v4
        with:
          name: earnings-v4-results
          path: "*.csv"
