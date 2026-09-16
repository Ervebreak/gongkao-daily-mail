#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="$ROOT_DIR/build/fc_package"
ZIP_PATH="$ROOT_DIR/function.zip"

cd "$ROOT_DIR"

rm -rf "$BUILD_DIR" "$ZIP_PATH"
mkdir -p "$BUILD_DIR"

# Copy source files and runtime assets.
# Keep this list explicit so generated outputs, private data, and .git metadata never enter the package.
find . -maxdepth 1 -type f \( -name "*.py" -o -name "requirements.txt" \) -exec cp {} "$BUILD_DIR" \;

for dir in agent content_harness knowledge scripts examples data; do
  if [ -d "$dir" ]; then
    mkdir -p "$BUILD_DIR/$dir"
    rsync -a \
      --exclude='__pycache__/' \
      --exclude='*.pyc' \
      --exclude='*.log' \
      --exclude='*.zip' \
      --exclude='*.pdf' \
      --exclude='*.xlsx' \
      --exclude='weekly_preview_fixed.json' \
      --exclude='validate_report_gate_test.json' \
      "$dir/" "$BUILD_DIR/$dir/"
  fi
done

python -m pip install --upgrade pip
python -m pip install -r requirements.txt -t "$BUILD_DIR"

cd "$BUILD_DIR"
zip -r "$ZIP_PATH" . \
  -x "*.git*" \
  -x "__pycache__/*" \
  -x "*.pyc" \
  -x "*.log"

cd "$ROOT_DIR"
echo "Built package: $ZIP_PATH"
