# shellcheck shell=bash
# Shared helper sourced by scripts/ship/ship and scripts/ship/ship-deploy.
# If the target repository pins a Node.js version in .nvmrc or .node-version,
# ensures that exact version is first on PATH (checking nvm, fnm, mise, volta).
# If no pin file exists, leaves PATH unchanged.

activate_node_version() {
  local repo="$1"
  local pin_file=""
  if [[ -f "$repo/.nvmrc" ]]; then
    pin_file="$repo/.nvmrc"
  elif [[ -f "$repo/.node-version" ]]; then
    pin_file="$repo/.node-version"
  else
    return 0
  fi

  local wanted
  wanted="$(tr -d '[:space:]' < "$pin_file")"
  wanted="${wanted#v}"
  if [[ -z "$wanted" ]]; then
    fail "$pin_file is empty"
  fi

  local current=""
  if command -v node >/dev/null 2>&1; then
    current="$(node --version 2>/dev/null || true)"
    current="${current#v}"
  fi
  if [[ "$current" == "$wanted" ]]; then
    return 0
  fi

  local nvm_dir="${NVM_DIR:-$HOME/.nvm}"
  local candidate_bin=""
  local dir
  for dir in \
    "$nvm_dir/versions/node/v$wanted/bin" \
    "$HOME/.local/share/fnm/node-versions/v$wanted/installation/bin" \
    "$HOME/.local/share/mise/installs/node/$wanted/bin" \
    "$HOME/.volta/tools/image/node/$wanted/bin"; do
    if [[ -x "$dir/node" ]]; then
      candidate_bin="$dir"
      break
    fi
  done

  if [[ -z "$candidate_bin" ]]; then
    fail "$pin_file pins Node v$wanted (PATH has ${current:-none}), and v$wanted is not installed locally (e.g. run: nvm install $wanted)"
  fi

  export PATH="$candidate_bin:$PATH"
}
