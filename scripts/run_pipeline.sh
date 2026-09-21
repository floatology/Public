#!/usr/bin/env bash
# The full pipeline, in the only order that works.
#
# Two constraints decide this ordering, and both were learned the hard way.
#
# **The RPC rate-limits globally, not per query.** During the first
# ten-thousand-pool extraction even a bare eth_blockNumber from a second process
# exhausted its retries. Stage 1 must therefore run alone: nothing else may
# touch the node while it is working, which is also why every later stage reads
# Parquet instead.
#
# **Stage 1 is the only stage that costs anything.** It is roughly ninety
# minutes of node time. Everything after it runs offline in seconds against the
# trade archive, so iterating on features means re-running stage 2, never
# stage 1.
#
# Usage:
#   scripts/run_pipeline.sh            # stages 2-6, offline
#   scripts/run_pipeline.sh --extract  # including the expensive stage 1
set -euo pipefail

cd "$(dirname "$0")/.."
PY=${PY:-.venv/bin/python}
SAMPLE=${SAMPLE:-10000}
THRESHOLD=${THRESHOLD:-10}

if [[ "${1:-}" == "--extract" ]]; then
  echo "== 1. extraction (RPC, exclusive, ~90 min) =============================="
  # This writes both the feature table and the trade archive. Without the
  # archive the wallet ledger below cannot run at all.
  # SKIP extends an earlier sample instead of redrawing one; write each
  # batch to its own file so the offline stages can read them together.
  SKIP=${SKIP:-0}
  $PY scripts/extract_features.py --sample "$SAMPLE" --skip "$SKIP" \
      --out "data/parquet/features_${SKIP}.parquet" \
      --trades-out "data/parquet/trades_${SKIP}.parquet"
else
  echo "== 1. extraction SKIPPED (pass --extract to run it) ====================="
fi

echo "== 2. rebuild features from the archive (offline) ======================="
# Safe to re-run after any change to rhc.features or rhc.manipulation.
if compgen -G "data/parquet/trades*.parquet" > /dev/null; then
  $PY scripts/recompute_features.py
else
  echo "   no trade archive yet; keeping the extraction's own feature table"
fi

echo "== 3. cross-token wallet ledger (offline) ==============================="
# Aborts rather than writing output if its internal audit disagrees with the
# reference scorer, so a non-zero exit here means a leak, not a hiccup.
$PY scripts/wallet_ledger.py --threshold "$THRESHOLD" || {
  echo "   wallet ledger did not complete; continuing without its columns" >&2
}

echo "== 3b. coordination clustering (offline) ================================"
# Entity map from a training window, so a token is scored with links that
# existed before it launched.
$PY scripts/wallet_clusters.py || true

echo "== 3c. venue fragmentation (offline, from the census) ==================="
$PY scripts/fragmentation.py || true

echo "== 3d. join the side tables ============================================="
$PY scripts/enrich_features.py --no-social --no-contracts || true

echo "== 4. column diagnostics ================================================"
# Read this before believing anything below it.
$PY scripts/describe_features.py

echo "== 5. independent dimensions ============================================"
$PY scripts/feature_correlations.py || true

echo "== 6. model, against the shuffled-label floor ==========================="
# Refuses to run below 60 rows or 10 positives, by design.
$PY scripts/model_features.py --threshold "$THRESHOLD" || true

echo
echo "Done. The number that matters is in data/model_result.json: whether the"
echo "confirmation-half AUC beats the shuffled-label control. Nothing else in"
echo "the output is evidence of anything."
