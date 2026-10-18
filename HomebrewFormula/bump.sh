#!/usr/bin/env bash
# Point the beatsd formula at one release: rewrite its version line and the
# sha256 line of each archive, in place.
#
#   bump.sh <version> <sidecar-dir> [formula]
#
# <version> is the release without its leading v (0.9.1 for tag v0.9.1).
# <sidecar-dir> holds the four sha256 sidecars release-daemon.yml writes next
# to the archives, beatsd-{darwin,linux}-{arm64,amd64}.tar.gz.sha256, each in
# shasum's "<64 hex>  <filename>" form. [formula] defaults to the beatsd.rb
# beside this script.
#
# Only the version line and the four sha256 lines change; everything else in
# the formula is main's, reviewed in pull requests. Each sha256 line is the
# one right after the url line naming its archive.
#
# Every failure exits non-zero with a message on stderr and leaves the
# formula untouched. Bumping to the values already there leaves the file
# byte-identical. Runs on BSD (macOS) and GNU (ubuntu) userland alike: no
# sed -i, no GNU-only flags.
set -euo pipefail

export LC_ALL=C

die() {
	echo "bump.sh: $*" >&2
	exit 1
}

[ "$#" -eq 2 ] || [ "$#" -eq 3 ] ||
	die "usage: bump.sh <version, e.g. 0.9.1> <dir with the .sha256 sidecars> [formula]"

version=$1
sidecars=$2
formula=${3:-"$(cd "$(dirname "$0")" && pwd)/beatsd.rb"}
platforms="darwin-arm64 darwin-amd64 linux-arm64 linux-amd64"

# Plain N.N.N only. A leading v would put /vv0.9.1/ in the URLs, and a
# prerelease suffix is not something the formula ships.
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] ||
	die "version '$version' is not N.N.N (no leading v, no prerelease suffix)"
[ -d "$sidecars" ] || die "sidecar directory '$sidecars' does not exist"
[ -f "$formula" ] || die "formula '$formula' not found"

# sha_for <platform> prints the archive's checksum, or exits on a missing or
# malformed sidecar.
sha_for() {
	local archive="beatsd-$1.tar.gz"
	local sidecar="$sidecars/$archive.sha256"
	[ -f "$sidecar" ] || die "missing sidecar $sidecar"

	local sum name
	sum=$(awk 'NR == 1 { print $1 }' "$sidecar")
	name=$(awk 'NR == 1 { print $2 }' "$sidecar")
	[[ "$sum" =~ ^[0-9a-f]{64}$ ]] ||
		die "$sidecar: first field '$sum' is not 64 lowercase hex characters"
	# shasum writes the file name it hashed; a sidecar renamed onto the wrong
	# archive would otherwise put one platform's checksum on another's URL.
	# A leading * is shasum's binary-mode marker.
	[ "${name#\*}" = "$archive" ] ||
		die "$sidecar: names '$name', not $archive"
	printf '%s' "$sum"
}

sums=""
for platform in $platforms; do
	sums="$sums $platform=$(sha_for "$platform")"
done

# shape <file> prints what bump.sh relies on in a formula, one fact a line:
#   version <count of version lines> <the last one's value>
#   url <platform> <count of url lines naming its archive>
#   sha256 <platform> <count of those followed by a sha256 line> <its value>
# The awk programs below and this one agree on what the lines look like.
shape() {
	awk -v platforms="$platforms" '
		BEGIN { n = split(platforms, p, " ") }
		pending != "" {
			if ($0 ~ /^[ \t]*sha256 "[^"]*"[ \t]*$/) {
				pairs[pending]++
				split($0, q, "\"")
				value[pending] = q[2]
			}
			pending = ""
		}
		/^[ \t]*version "[^"]*"[ \t]*$/ {
			versions++
			split($0, q, "\"")
			current = q[2]
		}
		/^[ \t]*url "/ {
			for (i = 1; i <= n; i++) {
				if (index($0, "/beatsd-" p[i] ".tar.gz\"")) {
					urls[p[i]]++
					pending = p[i]
				}
			}
		}
		END {
			printf "version %d %s\n", versions, current
			for (i = 1; i <= n; i++) {
				printf "url %s %d\n", p[i], urls[p[i]]
				printf "sha256 %s %d %s\n", p[i], pairs[p[i]], value[p[i]]
			}
		}
	' "$1"
}

# Refuse a formula whose shape bump.sh would rewrite wrongly or partly.
before=$(shape "$formula")
problems=""
while read -r kind a b _; do
	case "$kind" in
	version) [ "$a" = 1 ] || problems="$problems
  $a version lines, not exactly one" ;;
	url) [ "$b" = 1 ] || problems="$problems
  $b url lines naming beatsd-$a.tar.gz, not exactly one" ;;
	sha256) [ "$b" = 1 ] || problems="$problems
  $b url lines for beatsd-$a.tar.gz followed by a sha256 line, not exactly one" ;;
	esac
done <<<"$before"
[ -z "$problems" ] || die "$formula does not have the shape bump.sh rewrites:$problems"

# Write beside the formula, so the final mv is a rename on one filesystem,
# and copy it first, so the rewrite keeps the formula's permissions.
dir=$(dirname "$formula")
tmp=$(mktemp "$dir/.beatsd.rb.XXXXXX")
trap 'rm -f "$tmp"' EXIT
cp -p "$formula" "$tmp"

awk -v platforms="$platforms" -v version="$version" -v sums="$sums" '
	BEGIN {
		n = split(platforms, p, " ")
		m = split(sums, s, " ")
		for (i = 1; i <= m; i++) {
			split(s[i], kv, "=")
			sum[kv[1]] = kv[2]
		}
	}
	{
		line = $0
		if (pending != "") {
			if (line ~ /^[ \t]*sha256 "[^"]*"[ \t]*$/) {
				sub(/"[^"]*"/, "\"" sum[pending] "\"", line)
			}
			pending = ""
		} else if (line ~ /^[ \t]*version "[^"]*"[ \t]*$/) {
			sub(/"[^"]*"/, "\"" version "\"", line)
		} else if (line ~ /^[ \t]*url "/) {
			for (i = 1; i <= n; i++) {
				if (index(line, "/beatsd-" p[i] ".tar.gz\"")) pending = p[i]
			}
		}
		print line
	}
' "$formula" >"$tmp"

# The rewritten file must have the same shape, now carrying the new values.
want="version 1 $version"
for platform in $platforms; do
	sum=""
	for kv in $sums; do
		[ "${kv%%=*}" = "$platform" ] && sum=${kv#*=}
	done
	want="$want
url $platform 1
sha256 $platform 1 $sum"
done
after=$(shape "$tmp")
[ "$after" = "$want" ] || die "the rewritten formula is not what was meant; left $formula as it was.
wanted:
$want
got:
$after"

if cmp -s "$tmp" "$formula"; then
	echo "bump.sh: $formula already names beatsd $version and these checksums"
	exit 0
fi
mv "$tmp" "$formula"
trap - EXIT
echo "bump.sh: $formula now names beatsd $version"
