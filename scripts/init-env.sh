#!/bin/sh
# Generates .env from .env.example with random database credentials.
# Never overwrites an existing .env.
set -eu
root="$(cd "$(dirname "$0")/.." && pwd)"
example="$root/.env.example"
target="$root/.env"

if [ -e "$target" ]; then
  echo ".env already exists - leaving it unchanged."
  exit 0
fi

umask 077
: > "$target"
while IFS= read -r line || [ -n "$line" ]; do
  case "$line" in
    *=CHANGE_ME)
      key="${line%%=*}"
      printf '%s=%s\n' "$key" "$(openssl rand -hex 24)" >> "$target"
      ;;
    *)
      printf '%s\n' "$line" >> "$target"
      ;;
  esac
done < "$example"
echo "Created .env with generated credentials. It is git-ignored; do not commit it."
