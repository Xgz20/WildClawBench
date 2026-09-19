#!/bin/bash
set -euo pipefail

schema_version="wildclawbench.macos-desktop-debug-restart/v1"
job_label="com.wildclawbench.desktop-debug-restart.codex"
application="codex"
app_path=""
app_discovery_source=""
port=9230
delay_seconds=3
timeout_seconds=60
status_root="${HOME}/Library/Application Support/WildClawBench/desktop-debug-restart"
mode="schedule"
job_uid=""
state_dir=""
plist_path=""
run_id=""
created_at=""

launchctl_bin="${WCB_MACOS_LAUNCHCTL_BIN:-/bin/launchctl}"
uname_bin="${WCB_MACOS_UNAME_BIN:-/usr/bin/uname}"
id_bin="${WCB_MACOS_ID_BIN:-/usr/bin/id}"
uuidgen_bin="${WCB_MACOS_UUIDGEN_BIN:-/usr/bin/uuidgen}"
lsof_bin="${WCB_MACOS_LSOF_BIN:-/usr/sbin/lsof}"
ps_bin="${WCB_MACOS_PS_BIN:-/bin/ps}"
kill_bin="${WCB_MACOS_KILL_BIN:-/bin/kill}"
open_bin="${WCB_MACOS_OPEN_BIN:-/usr/bin/open}"
curl_bin="${WCB_MACOS_CURL_BIN:-/usr/bin/curl}"
sleep_bin="${WCB_MACOS_SLEEP_BIN:-/bin/sleep}"
date_bin="${WCB_MACOS_DATE_BIN:-/bin/date}"
plutil_bin="${WCB_MACOS_PLUTIL_BIN:-/usr/bin/plutil}"
nohup_bin="${WCB_MACOS_NOHUP_BIN:-/usr/bin/nohup}"

script_dir="$(cd "$(dirname "$0")" && pwd -P)"
script_path="$script_dir/$(basename "$0")"
discovery_cli="$script_dir/../desktop-app-discovery/cli.mjs"
if [[ ! -f "$discovery_cli" ]]; then
  discovery_cli="$script_dir/../vendor/e2e-shared/desktop-app-discovery/cli.mjs"
fi
node_bin="${WCB_NODE_BIN:-}"

usage() {
  cat <<'EOF'
Usage: restart_macos_desktop_debug.sh [options]

Schedule one managed restart of the Codex Desktop app on macOS.

Options:
  --application codex       Only codex is currently supported.
  --app-path PATH           Explicit ChatGPT.app or Codex.app path.
  --port PORT               Loopback CDP port. Default: 9230.
  --delay-seconds N         Delay before the worker quits Codex. Default: 3.
  --timeout-seconds N       CDP readiness timeout. Default: 60.
  --status-root PATH        Persistent status/log root.
  -h, --help                Show this help.

The command prints the status directory and exits after registering a
RunAtLoad=true, KeepAlive=false one-shot LaunchAgent through bootstrap.
EOF
}

while (( $# > 0 )); do
  case "$1" in
    --application)
      application="${2:-}"
      shift 2
      ;;
    --app-path)
      app_path="${2:-}"
      shift 2
      ;;
    --app-discovery-source)
      app_discovery_source="${2:-}"
      shift 2
      ;;
    --port)
      port="${2:-}"
      shift 2
      ;;
    --delay-seconds)
      delay_seconds="${2:-}"
      shift 2
      ;;
    --timeout-seconds)
      timeout_seconds="${2:-}"
      shift 2
      ;;
    --status-root)
      status_root="${2:-}"
      shift 2
      ;;
    --worker)
      mode="worker"
      shift
      ;;
    --cleanup-worker)
      mode="cleanup"
      shift
      ;;
    --job-label)
      job_label="${2:-}"
      shift 2
      ;;
    --job-uid)
      job_uid="${2:-}"
      shift 2
      ;;
    --state-dir)
      state_dir="${2:-}"
      shift 2
      ;;
    --plist-path)
      plist_path="${2:-}"
      shift 2
      ;;
    --run-id)
      run_id="${2:-}"
      shift 2
      ;;
    --created-at)
      created_at="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ "$("$uname_bin" -s)" != "Darwin" ]]; then
  echo "This helper only supports macOS" >&2
  exit 2
fi
if [[ "$application" != "codex" ]]; then
  echo "Only --application codex is supported" >&2
  exit 2
fi
if [[ ! "$port" =~ ^[0-9]+$ ]] || (( port < 1024 || port > 65535 )); then
  echo "--port must be an integer from 1024 through 65535" >&2
  exit 2
fi
if [[ ! "$delay_seconds" =~ ^[0-9]+$ ]] || (( delay_seconds > 30 )); then
  echo "--delay-seconds must be an integer from 0 through 30" >&2
  exit 2
fi
if [[ ! "$timeout_seconds" =~ ^[0-9]+$ ]] || (( timeout_seconds < 1 || timeout_seconds > 120 )); then
  echo "--timeout-seconds must be an integer from 1 through 120" >&2
  exit 2
fi

json_escape() {
  local value="$1"
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  value="${value//$'\n'/\\n}"
  value="${value//$'\r'/\\r}"
  value="${value//$'\t'/\\t}"
  printf '%s' "$value"
}

xml_escape() {
  local value="$1"
  value="${value//&/&amp;}"
  value="${value//</&lt;}"
  value="${value//>/&gt;}"
  value="${value//\"/&quot;}"
  value="${value//\'/&apos;}"
  printf '%s' "$value"
}

utc_now() {
  "$date_bin" -u '+%Y-%m-%dT%H:%M:%SZ'
}

validate_app_bundle() {
  local candidate="$1"
  local bundle_id
  if [[ ! -d "$candidate" || ! -f "$candidate/Contents/Info.plist" ]]; then
    return 1
  fi
  bundle_id="$("$plutil_bin" -extract CFBundleIdentifier raw -o - "$candidate/Contents/Info.plist" 2>/dev/null)" || return 1
  [[ "$bundle_id" == "com.openai.codex" ]]
}

resolve_app_path() {
  local discovery_output discovered_path discovered_source ignored_executable
  if [[ -n "$app_path" ]]; then
    validate_app_bundle "$app_path" || {
      echo "--app-path is not a com.openai.codex application bundle: $app_path" >&2
      return 1
    }
    if [[ -z "$app_discovery_source" ]]; then
      app_discovery_source="explicit"
    fi
    return 0
  fi
  if [[ ! -f "$discovery_cli" ]]; then
    echo "Bundled desktop application discovery CLI was not found: $discovery_cli" >&2
    return 1
  fi
  if [[ -z "$node_bin" ]]; then
    node_bin="$(/usr/bin/which node 2>/dev/null || true)"
  fi
  if [[ -z "$node_bin" || ! -x "$node_bin" ]]; then
    echo "Node.js is required for Codex Desktop application discovery" >&2
    return 1
  fi
  discovery_output="$("$node_bin" "$discovery_cli" --profile codex --platform darwin --format tsv)" || return 1
  IFS=$'\t' read -r discovered_path discovered_source ignored_executable <<< "$discovery_output"
  if [[ -z "$discovered_path" || -z "$discovered_source" ]]; then
    echo "Codex Desktop application discovery returned an incomplete result" >&2
    return 1
  fi
  app_path="$discovered_path"
  app_discovery_source="$discovered_source"
  validate_app_bundle "$app_path" || {
    echo "Discovered path is not a com.openai.codex application bundle: $app_path" >&2
    return 1
  }
}

write_status() {
  local status="$1"
  local error_message="${2:-}"
  local temporary="$status_path.tmp.$$"
  local error_json="null"
  if [[ -n "$error_message" ]]; then
    error_json="\"$(json_escape "$error_message")\""
  fi
  /usr/bin/printf '{\n  "schema_version": "%s",\n  "status": "%s",\n  "application": "codex",\n  "job_label": "%s",\n  "run_id": "%s",\n  "created_at": "%s",\n  "updated_at": "%s",\n  "port": %s,\n  "app_path": "%s",\n  "app_discovery_source": "%s",\n  "state_dir": "%s",\n  "error": %s\n}\n' \
    "$schema_version" \
    "$status" \
    "$(json_escape "$job_label")" \
    "$(json_escape "$run_id")" \
    "$(json_escape "$created_at")" \
    "$(utc_now)" \
    "$port" \
    "$(json_escape "$app_path")" \
    "$(json_escape "$app_discovery_source")" \
    "$(json_escape "$state_dir")" \
    "$error_json" > "$temporary"
  /bin/mv -f "$temporary" "$status_path"
}

listener_pid() {
  "$lsof_bin" -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null | /usr/bin/head -n 1 || true
}

listener_owned_by_app() {
  local pid="$1"
  local command
  command="$("$ps_bin" -p "$pid" -o command= 2>/dev/null)" || return 1
  [[ "$command" == "$app_path/Contents/MacOS/"* ]]
}

assert_port_restartable() {
  local pid
  pid="$(listener_pid)"
  if [[ -z "$pid" ]]; then
    return 0
  fi
  if ! listener_owned_by_app "$pid"; then
    echo "Port $port is owned by an unrelated process (PID $pid); refusing to restart" >&2
    return 1
  fi
}

app_main_pids() {
  local prefix="${app_path}/Contents/MacOS/"
  "$ps_bin" -axo pid=,ppid=,command= | /usr/bin/awk -v prefix="$prefix" '
    {
      pid = $1
      ppid = $2
      command = $0
      sub(/^[[:space:]]*[0-9]+[[:space:]]+[0-9]+[[:space:]]+/, "", command)
      if (index(command, prefix) == 1) {
        matched[pid] = 1
        parent[pid] = ppid
        ordered[++count] = pid
      }
    }
    END {
      for (idx = 1; idx <= count; idx += 1) {
        pid = ordered[idx]
        if (!(parent[pid] in matched)) print pid
      }
    }
  '
}

app_is_running() {
  [[ -n "$(app_main_pids)" ]]
}

process_matches_app_path() {
  local pid="$1"
  local command
  command="$("$ps_bin" -p "$pid" -o command= 2>/dev/null || true)"
  [[ -n "$command" && "$command" == "$app_path/Contents/MacOS/"* ]]
}

signal_app_processes() {
  local signal="$1"
  local pids pid
  pids="$(app_main_pids)"
  if [[ -z "$pids" ]]; then
    return 0
  fi
  while read -r pid; do
    [[ -n "$pid" ]] || continue
    if ! process_matches_app_path "$pid"; then
      echo "Codex Desktop process identity changed before $signal; refusing to signal PID $pid" >&2
      return 1
    fi
    if ! "$kill_bin" "-$signal" "$pid" 2>/dev/null && process_matches_app_path "$pid"; then
      echo "Unable to send $signal to verified Codex Desktop PID $pid" >&2
      return 1
    fi
  done <<< "$pids"
}

stop_app() {
  local attempt
  if ! app_is_running; then
    return 0
  fi
  echo "Stopping Codex Desktop for one managed restart..."
  signal_app_processes TERM
  for attempt in {1..20}; do
    if ! app_is_running; then
      return 0
    fi
    "$sleep_bin" 0.5
  done
  signal_app_processes KILL
  "$sleep_bin" 1
  if app_is_running; then
    echo "Unable to stop Codex Desktop" >&2
    return 1
  fi
}

cdp_ready() {
  local version targets pid
  version="$("$curl_bin" -fsS --max-time 2 "http://127.0.0.1:${port}/json/version" 2>/dev/null)" || return 1
  targets="$("$curl_bin" -fsS --max-time 2 "http://127.0.0.1:${port}/json/list" 2>/dev/null)" || return 1
  [[ "$version" == *'"webSocketDebuggerUrl"'* ]] || return 1
  [[ "$targets" == *'"webSocketDebuggerUrl"'* ]] || return 1
  pid="$(listener_pid)"
  [[ -n "$pid" ]] || return 1
  listener_owned_by_app "$pid"
}

start_app() {
  local pid
  pid="$(listener_pid)"
  if [[ -n "$pid" ]]; then
    echo "Port $port did not become free after Codex Desktop stopped" >&2
    return 1
  fi
  echo "Starting Codex Desktop with loopback CDP on port $port..."
  "$open_bin" -na "$app_path" --args \
    "--remote-debugging-address=127.0.0.1" \
    "--remote-debugging-port=${port}"
}

wait_for_cdp() {
  local deadline
  deadline=$(( $("$date_bin" +%s) + timeout_seconds ))
  while (( $("$date_bin" +%s) < deadline )); do
    if cdp_ready; then
      return 0
    fi
    "$sleep_bin" 0.5
  done
  echo "Codex Desktop CDP did not become ready on port $port within $timeout_seconds seconds" >&2
  return 1
}

validate_worker_identity() {
  if [[ "$job_label" != "com.wildclawbench.desktop-debug-restart.codex" ]]; then
    echo "Unexpected managed restart job label" >&2
    return 1
  fi
  if [[ -z "$job_uid" || ! "$job_uid" =~ ^[0-9]+$ ]]; then
    echo "Managed restart worker requires a numeric --job-uid" >&2
    return 1
  fi
  if [[ -z "$state_dir" || "$plist_path" != "$state_dir/job.plist" ]]; then
    echo "Managed restart worker received an invalid state/plist path" >&2
    return 1
  fi
}

schedule_cleanup() {
  "$nohup_bin" /bin/bash "$script_path" \
    --cleanup-worker \
    --job-label "$job_label" \
    --job-uid "$job_uid" \
    --state-dir "$state_dir" \
    --plist-path "$plist_path" \
    --app-path "$app_path" \
    --app-discovery-source "$app_discovery_source" \
    --port "$port" \
    --delay-seconds 0 \
    --timeout-seconds "$timeout_seconds" \
    >/dev/null 2>&1 &
}

run_cleanup_worker() {
  validate_worker_identity
  "$sleep_bin" 1
  "$launchctl_bin" bootout "gui/${job_uid}/${job_label}" >/dev/null 2>&1 || true
  if [[ -f "$plist_path" && "$plist_path" == "$state_dir/job.plist" ]]; then
    /bin/rm -f -- "$plist_path"
  fi
}

run_restart_worker() {
  local code
  status_path="$state_dir/status.json"
  validate_worker_identity || return 1
  write_status "RUNNING"
  code=0
  if ! resolve_app_path; then
    code=1
  elif ! "$sleep_bin" "$delay_seconds"; then
    code=1
  elif assert_port_restartable && stop_app && assert_port_restartable && start_app && wait_for_cdp; then
    write_status "PASSED"
  else
    code=$?
  fi
  if (( code != 0 )); then
    write_status "FAILED" "Managed restart worker exited with code $code; see stderr.log"
  fi
  schedule_cleanup
  return "$code"
}

render_plist() {
  local stdout_path="$state_dir/stdout.log"
  local stderr_path="$state_dir/stderr.log"
  /usr/bin/printf '%s\n' \
    '<?xml version="1.0" encoding="UTF-8"?>' \
    '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">' \
    '<plist version="1.0">' \
    '<dict>' \
    '  <key>Label</key>' \
    "  <string>$(xml_escape "$job_label")</string>" \
    '  <key>ProgramArguments</key>' \
    '  <array>' \
    '    <string>/bin/bash</string>' \
    "    <string>$(xml_escape "$script_path")</string>" \
    '    <string>--worker</string>' \
    '    <string>--job-label</string>' \
    "    <string>$(xml_escape "$job_label")</string>" \
    '    <string>--job-uid</string>' \
    "    <string>$(xml_escape "$job_uid")</string>" \
    '    <string>--state-dir</string>' \
    "    <string>$(xml_escape "$state_dir")</string>" \
    '    <string>--plist-path</string>' \
    "    <string>$(xml_escape "$plist_path")</string>" \
    '    <string>--run-id</string>' \
    "    <string>$(xml_escape "$run_id")</string>" \
    '    <string>--created-at</string>' \
    "    <string>$(xml_escape "$created_at")</string>" \
    '    <string>--app-path</string>' \
    "    <string>$(xml_escape "$app_path")</string>" \
    '    <string>--app-discovery-source</string>' \
    "    <string>$(xml_escape "$app_discovery_source")</string>" \
    '    <string>--port</string>' \
    "    <string>$(xml_escape "$port")</string>" \
    '    <string>--delay-seconds</string>' \
    "    <string>$(xml_escape "$delay_seconds")</string>" \
    '    <string>--timeout-seconds</string>' \
    "    <string>$(xml_escape "$timeout_seconds")</string>" \
    '  </array>' \
    '  <key>RunAtLoad</key>' \
    '  <true/>' \
    '  <key>KeepAlive</key>' \
    '  <false/>' \
    '  <key>AbandonProcessGroup</key>' \
    '  <true/>' \
    '  <key>ProcessType</key>' \
    '  <string>Background</string>' \
    '  <key>StandardOutPath</key>' \
    "  <string>$(xml_escape "$stdout_path")</string>" \
    '  <key>StandardErrorPath</key>' \
    "  <string>$(xml_escape "$stderr_path")</string>" \
    '</dict>' \
    '</plist>' > "$plist_path"
}

schedule_restart() {
  local legacy_label
  job_uid="$("$id_bin" -u)"
  resolve_app_path
  for legacy_label in \
    "com.wildclawbench.general-e2e.codex-debug" \
    "com.wildclawbench.general-e2e.codex-refresh"; do
    if "$launchctl_bin" print "gui/${job_uid}/${legacy_label}" >/dev/null 2>&1; then
      echo "Legacy restart job is still active: $legacy_label; remove it before scheduling a restart" >&2
      return 1
    fi
  done
  if "$launchctl_bin" print "gui/${job_uid}/${job_label}" >/dev/null 2>&1; then
    echo "A managed Codex restart is already registered: $job_label" >&2
    return 1
  fi

  created_at="$(utc_now)"
  run_id="$("$date_bin" -u '+%Y%m%dT%H%M%SZ')-$$-$("$uuidgen_bin" | /usr/bin/tr '[:upper:]' '[:lower:]')"
  state_dir="$status_root/$run_id"
  plist_path="$state_dir/job.plist"
  status_path="$state_dir/status.json"
  /bin/mkdir -p "$state_dir"
  : > "$state_dir/stdout.log"
  : > "$state_dir/stderr.log"
  render_plist
  write_status "SCHEDULED"

  if ! "$launchctl_bin" bootstrap "gui/${job_uid}" "$plist_path"; then
    write_status "FAILED" "launchctl bootstrap failed; see stderr.log"
    /bin/rm -f -- "$plist_path"
    return 1
  fi
  /usr/bin/printf 'Scheduled one Codex Desktop restart.\nStatus: %s\nLogs: %s, %s\n' \
    "$status_path" "$state_dir/stdout.log" "$state_dir/stderr.log"
}

case "$mode" in
  schedule)
    schedule_restart
    ;;
  worker)
    run_restart_worker
    ;;
  cleanup)
    run_cleanup_worker
    ;;
  *)
    echo "Unsupported mode: $mode" >&2
    exit 2
    ;;
esac
