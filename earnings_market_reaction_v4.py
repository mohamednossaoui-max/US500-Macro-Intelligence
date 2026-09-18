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

      # ==================================================
      # 1. Checkout repository
      # ==================================================

      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          ref: ${{ github.ref }}
          fetch-depth: 0

      # ==================================================
      # 2. Setup Python
      # ==================================================

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      # ==================================================
      # 3. Verify files
      # ==================================================

      - name: Verify repository files
        run: |
          echo "=========================================="
          echo "REPOSITORY"
          echo "=========================================="

          pwd

          echo ""
          echo "Branch:"
          git branch --show-current

          echo ""
          echo "Commit:"
          git log -1 --oneline

          echo ""
          echo "Earnings Python files:"
          ls -lh *earning*.py

          echo ""
          echo "Checking V2..."
          test -f earnings_breadth_v2.py
          echo "V2 script FOUND."

          echo ""
          echo "Checking V4..."
          test -f earnings_market_reaction_v4.py
          echo "V4 script FOUND."

          echo ""
          echo "=========================================="
          echo "REPOSITORY CHECK PASSED"
          echo "=========================================="

      # ==================================================
      # 4. Install dependencies
      # ==================================================

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      # ==================================================
      # 5. Run V2
      # ==================================================

      - name: Run Earnings Breadth V2
        env:
          ALPHAVANTAGE_API_KEY: ${{ secrets.ALPHAVANTAGE_API_KEY }}
        run: |
          echo "=========================================="
          echo "RUNNING EARNINGS BREADTH V2"
          echo "=========================================="

          python earnings_breadth_v2.py

      # ==================================================
      # 6. Verify V2 output
      # ==================================================

      - name: Verify V2 output
        run: |
          echo "=========================================="
          echo "CHECKING V2 OUTPUT"
          echo "=========================================="

          test -f earnings_breadth_events_v2.csv

          echo "V2 output FOUND:"
          ls -lh earnings_breadth_events_v2.csv

          echo ""
          echo "V2 output preview:"
          head -n 5 earnings_breadth_events_v2.csv

      # ==================================================
      # 7. Run V4
      # ==================================================

      - name: Run Corporate Earnings Intelligence V4
        run: |
          echo "=========================================="
          echo "RUNNING CORPORATE EARNINGS INTELLIGENCE V4"
          echo "=========================================="

          python earnings_market_reaction_v4.py

      # ==================================================
      # 8. Verify V4 outputs
      # ==================================================

      - name: Verify V4 outputs
        run: |
          echo "=========================================="
          echo "CHECKING V4 OUTPUT FILES"
          echo "=========================================="

          test -f earnings_market_reaction_v4.csv
          test -f earnings_event_study_v4.csv
          test -f earnings_abnormal_return_v4.csv
          test -f earnings_market_reaction_summary_v4.csv
          test -f earnings_reaction_by_eps_class_v4.csv
          test -f earnings_reaction_by_sector_v4.csv

          echo ""
          echo "ALL V4 OUTPUT FILES CREATED SUCCESSFULLY."

          echo ""
          echo "Generated files:"
          ls -lh \
            earnings_market_reaction_v4.csv \
            earnings_event_study_v4.csv \
            earnings_abnormal_return_v4.csv \
            earnings_market_reaction_summary_v4.csv \
            earnings_reaction_by_eps_class_v4.csv \
            earnings_reaction_by_sector_v4.csv

      # ==================================================
      # 9. Show important results
      # ==================================================

      - name: Display V4 summary
        run: |
          echo "=========================================="
          echo "V4 SUMMARY"
          echo "=========================================="

          cat earnings_market_reaction_summary_v4.csv

          echo ""
          echo "=========================================="
          echo "EPS CLASS SUMMARY"
          echo "=========================================="

          cat earnings_reaction_by_eps_class_v4.csv

          echo ""
          echo "=========================================="
          echo "SECTOR SUMMARY"
          echo "=========================================="

          cat earnings_reaction_by_sector_v4.csv

      # ==================================================
      # 10. Upload results
      # ==================================================

      - name: Upload V4 results
        uses: actions/upload-artifact@v4
        with:
          name: corporate-earnings-intelligence-v4-results
          path: |
            earnings_breadth_events_v2.csv
            earnings_market_reaction_v4.csv
            earnings_event_study_v4.csv
            earnings_abnormal_return_v4.csv
            earnings_market_reaction_summary_v4.csv
            earnings_reaction_by_eps_class_v4.csv
            earnings_reaction_by_sector_v4.csv
