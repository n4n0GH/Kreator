#!/bin/sh
# Make a release of the version in kreator/__init__.py:
#   - a signed tag  v<version>
#   - dist/kreator-<version>.tar.gz with its signature (.asc) and checksum (.sha256)
#   - the GitHub release, with the version's section of CHANGELOG.md as its notes
#
#   tools/release.sh
#
# Needs the keyring with the release signing key (its public half is
# docs/signing-key.asc) in ~/.local/share/kreator-signing, or where
# KREATOR_SIGNING_HOME says, and GitHub's `gh`, logged in.
set -eu

cd "$(dirname "$(readlink -f "$0")")/.."

KEYS="${KREATOR_SIGNING_HOME:-$HOME/.local/share/kreator-signing}"
FPR=33DF82C4E8B1F312C294ECD1664E00DD15201C7C

die() {
    echo "release: $*" >&2
    exit 1
}

V=$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' kreator/__init__.py)
[ -n "$V" ] || die "no version in kreator/__init__.py"
TAG="v$V"
grep -q "^version = \"$V\"\$" pyproject.toml || die "pyproject.toml's version is not $V"
[ "$(git rev-parse --abbrev-ref HEAD)" = main ] || die "not on main"
[ -z "$(git status --porcelain)" ] || die "there are uncommitted changes"
if git rev-parse -q --verify "refs/tags/$TAG" > /dev/null; then
    die "the tag $TAG exists already"
fi
gpg --homedir "$KEYS" --batch --list-secret-keys "$FPR" > /dev/null 2>&1 \
    || die "the signing key $FPR is not in $KEYS"

# the notes: the version's section of the changelog
NOTES=$(mktemp)
trap 'rm -f "$NOTES"' EXIT
awk -v v="$V" '/^## / { on = ($2 == v); next } on' CHANGELOG.md > "$NOTES"
grep -q '[^[:space:]]' "$NOTES" || die "CHANGELOG.md has no section \"## $V\""

GNUPGHOME="$KEYS" git tag -s -u "$FPR" -m "Kreator $V" "$TAG"
GNUPGHOME="$KEYS" git verify-tag "$TAG"

mkdir -p dist
NAME="kreator-$V.tar.gz"
git archive --format=tar.gz --prefix="kreator-$V/" -o "dist/$NAME" "$TAG"
gpg --homedir "$KEYS" --batch --yes -u "$FPR" --armor --detach-sign -o "dist/$NAME.asc" "dist/$NAME"
(cd dist && sha256sum "$NAME" > "$NAME.sha256")
gpg --homedir "$KEYS" --batch --verify "dist/$NAME.asc" "dist/$NAME"

git push origin main "$TAG"
gh release create "$TAG" "dist/$NAME" "dist/$NAME.asc" "dist/$NAME.sha256" \
    --verify-tag --title "Kreator $V" --notes-file "$NOTES"
