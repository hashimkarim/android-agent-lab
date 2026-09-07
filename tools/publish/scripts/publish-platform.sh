#!/usr/bin/env bash
# Validate exactly the prepared release. Publication is opt-in; credentials never enter containers.
set -euo pipefail
platform="${1:?platform required}"
package_dir="$(realpath "${2:?prepared directory required}")"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
: "${RELEASE_TAG:?}"
[[ "$RELEASE_TAG" =~ ^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]] || exit 1
version="${RELEASE_TAG#v}"
dry_run="${DRY_RUN:-true}"
[[ "$dry_run" == true || "$dry_run" == false ]] || exit 1
case "$platform" in
  aur) image=archlinux:base-devel; check=arch ;;
  homebrew) image=homebrew/brew:latest; check=homebrew ;;
  copr) image=fedora:44; check=fedora ;;
  ppa) image=ubuntu:24.04; check=ubuntu ;;
  *) echo "Unknown publishing platform: $platform" >&2; exit 1 ;;
esac
python3 - "$package_dir/manifest.json" "$RELEASE_TAG" <<'PY'
import json, sys
if json.load(open(sys.argv[1]))['tag'] != sys.argv[2]:
    raise SystemExit('Prepared package does not match RELEASE_TAG')
PY

require_value() {
  if [[ -z "${!1:-}" ]]; then
    echo "::error::Missing repository secret/variable $1. See docs/distribution.md."
    exit 1
  fi
}
if [[ "$dry_run" == false ]]; then
  case "$platform" in
    aur) require_value AUR_SSH_PRIVATE_KEY; require_value AUR_SSH_KNOWN_HOSTS ;;
    homebrew) require_value HOMEBREW_SSH_PRIVATE_KEY; require_value HOMEBREW_TAP_REPOSITORY ;;
    copr) require_value COPR_CONFIG ;;
    ppa) require_value PPA_GPG_PRIVATE_KEY; require_value PPA_GPG_FINGERPRINT ;;
  esac
fi

# Output contains only public package files. All installation tests use disposable containers.
results="$package_dir/results/$platform"
mkdir -p "$results"
docker run --rm --cap-add SYS_ADMIN --cpus 2 --memory 4g \
  -e PUBLISH_UID="$(id -u)" -e PUBLISH_GID="$(id -g)" \
  -v "$package_dir:/prepared:ro" -v "$results:/results" \
  -v "$script_dir/../checks:/checks:ro" "$image" bash "/checks/$check.sh"

if [[ "$dry_run" == true ]]; then
  echo "$platform: $RELEASE_TAG package build, installation and smoke test passed (dry run)."
  if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
    echo "- $platform: $RELEASE_TAG package installation and smoke test passed; nothing published." >> "$GITHUB_STEP_SUMMARY"
  fi
  exit 0
fi

assert_latest() { python3 "$script_dir/release-info.py" "$RELEASE_TAG" > /dev/null; }
assert_latest
private_dir="$(mktemp -d)"
chmod 700 "$private_dir"
cleanup() {
  if [[ -n "${GNUPGHOME:-}" && "$GNUPGHOME" == "$private_dir/gpg" ]]; then
    gpgconf --kill gpg-agent || true
  fi
  rm -rf -- "$private_dir"
}
trap cleanup EXIT

ssh_setup() {
  chmod 600 "$private_dir/key" "$private_dir/known_hosts"
  printf -v GIT_SSH_COMMAND 'ssh -i %q -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=%q' "$private_dir/key" "$private_dir/known_hosts"
  export GIT_SSH_COMMAND
}
commit_and_push() {
  git config user.name 'Android Agent Lab release bot'
  git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
  if git diff --cached --quiet; then
    echo "$platform already contains $RELEASE_TAG"
  else
    assert_latest
    git commit -m "Release $RELEASE_TAG"
    git push origin HEAD
  fi
}
check_recipe_version() {
  python3 "$script_dir/recipe-version.py" "$1" "$platform" "$version"
}
skip_existing() {
  local status=0
  check_recipe_version "$1" || status=$?
  if [[ "$status" == 10 ]]; then return 0; fi
  if [[ "$status" != 0 ]]; then exit "$status"; fi
  return 1
}

case "$platform" in
  aur)
    printf '%s\n' "$AUR_SSH_PRIVATE_KEY" > "$private_dir/key"
    printf '%s\n' "$AUR_SSH_KNOWN_HOSTS" > "$private_dir/known_hosts"
    ssh_setup
    git clone ssh://aur@aur.archlinux.org/android-agent-lab-bin.git "$private_dir/repo"
    cd "$private_dir/repo"
    if ! skip_existing PKGBUILD; then
      cp "$package_dir/aur/PKGBUILD" "$results/.SRCINFO" .
      git add PKGBUILD .SRCINFO
      commit_and_push
    fi
    ;;
  homebrew)
    [[ "$HOMEBREW_TAP_REPOSITORY" == hashimkarim/homebrew-tap ]] || { echo 'Unexpected Homebrew destination' >&2; exit 1; }
    printf '%s\n' "$HOMEBREW_SSH_PRIVATE_KEY" > "$private_dir/key"
    python3 - <<'PY' > "$private_dir/known_hosts"
import json, urllib.request
with urllib.request.urlopen('https://api.github.com/meta', timeout=30) as response:
    for key in json.load(response)['ssh_keys']:
        print('github.com ' + key)
PY
    ssh_setup
    git clone "git@github.com:$HOMEBREW_TAP_REPOSITORY.git" "$private_dir/repo"
    cd "$private_dir/repo"
    if ! skip_existing Formula/android-agent-lab.rb; then
      mkdir -p Formula
      cp "$package_dir/homebrew/Formula/android-agent-lab.rb" Formula/
      git add Formula/android-agent-lab.rb
      commit_and_push
    fi
    ;;
  copr|ppa)
    status=0
    python3 "$script_dir/publication-state.py" "$platform" "$version" || status=$?
    if [[ "$status" == 2 ]]; then exit 2; fi
    if [[ "$status" != 0 && "$status" != 1 ]]; then exit "$status"; fi
    if [[ "$platform" == copr ]]; then
      assert_latest
      printf '%s\n' "$COPR_CONFIG" > "$private_dir/copr"
      chmod 600 "$private_dir/copr"
      timeout 300 python3 "$script_dir/sync-copr-metadata.py" "$private_dir/copr" \
        hashimkarim/android-agent-lab "$script_dir/../../../packaging/copr/project.json"
    fi
    if [[ "$status" == 1 ]]; then
      assert_latest
      if [[ "$platform" == copr ]]; then
        timeout 300 copr-cli --config "$private_dir/copr" build --nowait hashimkarim/android-agent-lab "$results/"*.src.rpm
      else
        export GNUPGHOME="$private_dir/gpg"
        mkdir -m 700 "$GNUPGHOME"
        printf '%s\n' "$PPA_GPG_PRIVATE_KEY" | gpg --batch --import
        printf '%s' "${PPA_GPG_PASSPHRASE:-}" > "$GNUPGHOME/passphrase"
        chmod 600 "$GNUPGHOME/passphrase"
        cat > "$GNUPGHOME/sign" <<'SIGN'
#!/bin/sh
exec gpg --batch --pinentry-mode loopback --passphrase-file "$GNUPGHOME/passphrase" "$@"
SIGN
        chmod 700 "$GNUPGHOME/sign"
        deb_version="$(python3 "$script_dir/publication-state.py" ppa "$version" --print-version)"
        changes="$results/android-agent-lab_${deb_version}_source.changes"
        debsign -p"$GNUPGHOME/sign" -k"$PPA_GPG_FINGERPRINT" "$changes"
        timeout 600 dput ppa:hashimkarim/android-agent-lab "$changes"
      fi
      python3 "$script_dir/publication-state.py" "$platform" "$version" --wait
    fi
    ;;
esac
if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
  echo "- $platform: $RELEASE_TAG is published (existing publications are reused)." >> "$GITHUB_STEP_SUMMARY"
fi
