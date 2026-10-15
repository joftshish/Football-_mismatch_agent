name: Fast Scan

on:
  schedule:
    - cron: '*/5 * * * *'
  workflow_dispatch:

concurrency:
  group: fast
  cancel-in-progress: false

jobs:
  fast:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install
        run: pip install httpx jdatetime
      - name: Restore state
        uses: actions/cache/restore@v4
        with:
          path: state.json
          key: state-${{ github.run_id }}
          restore-keys: state-
      - name: Restore tennis state
        uses: actions/cache/restore@v4
        with:
          path: tennis_state.json
          key: tennis-${{ github.run_id }}
          restore-keys: tennis-
      - name: Restore scan state
        uses: actions/cache/restore@v4
        with:
          path: scan_state.json
          key: scan-${{ github.run_id }}
          restore-keys: scan-
      - name: Restore vision state
        uses: actions/cache/restore@v4
        with:
          path: vision_state.json
          key: vision-${{ github.run_id }}
          restore-keys: vision-
      - name: Fast scan
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: python Fast.py
      - name: Run feed
        continue-on-error: true
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: python Feed.py
      - name: Run tennis
        continue-on-error: true
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: python Tennis.py
      - name: Run longshot
        continue-on-error: true
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: python LongShot.py
      - name: Run scan
        continue-on-error: true
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: python Scan.py
      - name: Run vision
        continue-on-error: true
        env:
          TELEGRAM_VISION_TOKEN: ${{ secrets.TELEGRAM_VISION_TOKEN }}
          TELEGRAM_VISION_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
        run: python Vision.py
      - name: Save state
        if: always()
        uses: actions/cache/save@v4
        with:
          path: state.json
          key: state-${{ github.run_id }}
      - name: Save tennis state
        if: always()
        uses: actions/cache/save@v4
        with:
          path: tennis_state.json
          key: tennis-${{ github.run_id }}
      - name: Save scan state
        if: always()
        uses: actions/cache/save@v4
        with:
          path: scan_state.json
          key: scan-${{ github.run_id }}
      - name: Save vision state
        if: always()
        uses: actions/cache/save@v4
        with:
          path: vision_state.json
          key: vision-${{ github.run_id }}
