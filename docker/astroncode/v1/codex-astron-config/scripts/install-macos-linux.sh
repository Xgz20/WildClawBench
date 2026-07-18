#!/bin/sh
set -eu

source_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
codex_home=${CODEX_HOME:-"$HOME/.acode"}
catalog_path="$codex_home/astron-spark.json"
profile_path="$codex_home/astron-spark.config.toml"
config_path="$codex_home/config.toml"

mkdir -p "$codex_home"
cp "$source_dir/config/astron-spark.json" "$catalog_path"
sed "s|__MODEL_CATALOG_PATH__|$catalog_path|g" \
  "$source_dir/config/astron-spark.config.toml.template" > "$profile_path"

if ! grep -q '^\[model_providers\.astron-spark\]$' "$config_path" 2>/dev/null; then
  if test -f "$config_path" && test -s "$config_path"; then
    printf '\n' >> "$config_path"
  fi
  cat "$source_dir/config/provider.toml" >> "$config_path"
fi

printf '已安装 Astron Spark 配置：%s\n' "$codex_home"
