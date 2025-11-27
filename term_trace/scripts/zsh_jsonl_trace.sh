LOGDIR="${ZSH_LOG_DIR:-$HOME/.zsh_logs}"
JSONL_LOG="${ZSH_JSONL_LOG:-$LOGDIR/session.jsonl}"
PY_HELPER="$(dirname ${(%):-%N})/write_jsonl_entry.py"

mkdir -p "$LOGDIR"

_zsh_jsonl_tmp=""
_zsh_jsonl_cmd=""
_zsh_jsonl_start=""

# Override the default zle accept-line widget to catch notes
_zsh_jsonl_accept_line() {
    local cmd="${BUFFER}"
    if [[ "$cmd" == \#* ]]; then
        # This is a note, process it immediately
        local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
        python3 "$PY_HELPER" "$JSONL_LOG" "$timestamp" "$cmd" "" "0"
    fi
    # Call the original accept-line widget
    zle .accept-line
}

# Create a new widget from our function and bind it
zle -N accept-line _zsh_jsonl_accept_line

_zsh_jsonl_preexec() {
    # Only process non-note commands
    if [[ "$1" != \#* ]]; then
        _zsh_jsonl_cmd="$1"
        _zsh_jsonl_start=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
        _zsh_jsonl_tmp=$(mktemp "$LOGDIR/output.XXXXXX")
        exec > >(tee -a "$_zsh_jsonl_tmp") 2>&1
    fi
}

_zsh_jsonl_precmd() {
    exit_code=$?
    exec > /dev/tty 2>&1
    if [[ -f "$_zsh_jsonl_tmp" ]]; then
        output=$(<"$_zsh_jsonl_tmp")
        python3 "$PY_HELPER" "$JSONL_LOG" "$_zsh_jsonl_start" "$_zsh_jsonl_cmd" "$output" "$exit_code"
        rm -f "$_zsh_jsonl_tmp"
        _zsh_jsonl_tmp=""
    fi
}

autoload -Uz add-zsh-hook
add-zsh-hook preexec _zsh_jsonl_preexec
add-zsh-hook precmd _zsh_jsonl_precmd
