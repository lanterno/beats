#!/usr/bin/env bash
# Serializes the API's deploys and refuses to roll the live API back.
#
# Every push to main that touches api/ or terraform/ starts a Cloud Build, and
# several merges within seconds start several builds at once. Terraform's own
# state lock makes all but one of them fail ("Error acquiring the state lock"),
# and waiting on it instead (-lock-timeout) would hand the lock out in no
# particular order: an older build could apply after a newer one and put the
# older image back. So api/cloudbuild.yaml wraps `terraform apply` in this:
#
#   acquire  wait for, then create, a mutex object in GCS. Creation is
#            conditional on no object existing (if-generation-match=0), so
#            exactly one build holds it. A mutex older than
#            DEPLOY_LOCK_STALE_SECONDS was left by a build that was killed
#            mid-deploy; it is deleted, conditional on its generation so two
#            waiters cannot both break it, and the wait goes on. One whose age
#            cannot be read is never broken. One that names this build is its
#            own, made by a create whose response was lost and that gcloud
#            retried.
#   decide   holding the mutex, read the commit the Cloud Run service serves
#            (its latest ready revision, which is older than the spec when the
#            newest revision failed to start) and decide whether this build
#            deploys: "skip" when this build's commit is a strict ancestor of
#            the live one (a newer build got there first), "apply" otherwise.
#            Deciding inside the mutex is the point: no newer build can apply
#            between the check and this build's apply.
#   release  delete the mutex, conditional on the generation this build
#            created, so a build whose mutex was broken as stale never deletes
#            the one another build now holds.
#
# Configuration comes from the environment, and nothing deployment-specific has
# a default: a subcommand names any variable it needs that is unset.
#
#   DEPLOY_LOCK_OBJECT         gs:// URL of the mutex object (acquire, release)
#   DEPLOY_STATE_DIR           directory shared by the build's steps; holds
#                              lock-generation and decision (all)
#   DEPLOY_LOCK_STALE_SECONDS  age past which a mutex is presumed abandoned;
#                              well above the longest a deploy holds it (acquire)
#   DEPLOY_LOCK_WAIT_SECONDS   how long acquire waits in all; must exceed the
#                              stale threshold, or a waiter could give up before
#                              an abandoned mutex can be broken (acquire)
#   DEPLOY_LOCK_POLL_SECONDS   seconds between attempts; 10 if unset (acquire)
#   DEPLOY_RETRY_SECONDS       seconds before retrying a failed call; 5 if
#                              unset (release)
#   BUILD_ID, COMMIT_SHA       this build; written into the mutex so a stuck
#                              one says whose it is (acquire; COMMIT_SHA: decide)
#   CLOUD_RUN_SERVICE, CLOUD_RUN_REGION, GCP_PROJECT
#                              the service whose live image is compared (decide)
#   DEPLOY_REPO_URL            git URL holding main's history (decide)
#
# A stuck mutex can be cleared by hand: gcloud storage rm "$DEPLOY_LOCK_OBJECT"
set -euo pipefail

log() { printf '[deploy-lock] %s\n' "$*" >&2; }
die() {
	log "error: $*"
	exit 1
}

require() {
	local name missing=""
	for name in "$@"; do
		if [[ -z ${!name:-} ]]; then
			missing="$missing $name"
		fi
	done
	if [[ -n $missing ]]; then
		die "missing required environment variable(s):$missing"
	fi
}

require_seconds() {
	local name
	for name in "$@"; do
		[[ ${!name} =~ ^[1-9][0-9]*$ ]] || die "$name must be a positive whole number of seconds, got '${!name}'"
	done
}

is_sha() { [[ $1 =~ ^[0-9a-f]{40}$ ]]; }

acquire() {
	require DEPLOY_LOCK_OBJECT DEPLOY_STATE_DIR DEPLOY_LOCK_STALE_SECONDS \
		DEPLOY_LOCK_WAIT_SECONDS BUILD_ID COMMIT_SHA
	local poll=${DEPLOY_LOCK_POLL_SECONDS:-10}
	require_seconds DEPLOY_LOCK_STALE_SECONDS DEPLOY_LOCK_WAIT_SECONDS poll
	((DEPLOY_LOCK_WAIT_SECONDS > DEPLOY_LOCK_STALE_SECONDS)) ||
		die "DEPLOY_LOCK_WAIT_SECONDS ($DEPLOY_LOCK_WAIT_SECONDS) must exceed DEPLOY_LOCK_STALE_SECONDS ($DEPLOY_LOCK_STALE_SECONDS)"

	mkdir -p "$DEPLOY_STATE_DIR"
	local holder_file="$DEPLOY_STATE_DIR/lock-holder"
	local deadline=$(($(date +%s) + DEPLOY_LOCK_WAIT_SECONDS))
	local out info err gen held_gen created age content holder now
	local last_logged_gen="" polls=0 vanished=0
	while :; do
		# Stamped afresh on each attempt, so the mutex says when it was taken,
		# not when this build began to wait.
		printf 'build_id=%s\ncommit_sha=%s\nacquired_at=%s\n' \
			"$BUILD_ID" "$COMMIT_SHA" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >"$holder_file"
		if out=$(gcloud storage cp --if-generation-match=0 --print-created-message \
			"$holder_file" "$DEPLOY_LOCK_OBJECT" 2>&1); then
			# The created message ends in the version-specific URL, <object>#<generation>.
			gen=$(sed -n 's/.*Created: .*#\([0-9][0-9]*\).*/\1/p' <<<"$out" | tail -n 1)
			[[ -n $gen ]] || die "created $DEPLOY_LOCK_OBJECT but could not read its generation from:
$out
Remove it by hand: gcloud storage rm $DEPLOY_LOCK_OBJECT"
			printf '%s\n' "$gen" >"$DEPLOY_STATE_DIR/lock-generation"
			log "acquired $DEPLOY_LOCK_OBJECT (generation $gen) for build $BUILD_ID at $COMMIT_SHA"
			return 0
		fi

		# The create failed. Either someone holds the mutex, or something is wrong
		# with the bucket; only an object that exists tells the two apart.
		if ! info=$(gcloud storage objects describe "$DEPLOY_LOCK_OBJECT" \
			--format='value(generation,creation_time.date("%s"))' 2>&1); then
			# Released between the create and the look: try again at once. Any
			# other error waits a poll first. A create that keeps failing while
			# the object cannot be seen is a broken bucket.
			vanished=$((vanished + 1))
			((vanished < 3)) || die "cannot create $DEPLOY_LOCK_OBJECT, and cannot see it:
$out
$info"
			[[ $info == *"not found: 404"* ]] || sleep "$poll"
			continue
		fi
		vanished=0
		held_gen="" created=""
		read -r held_gen created <<<"$info" || true
		created=${created%%.*}
		content=$(gcloud storage cat "$DEPLOY_LOCK_OBJECT#$held_gen" 2>/dev/null || true)
		holder=$(tr '\n' ' ' <<<"$content")
		holder=${holder% }

		# gcloud retries a create whose response was lost; the retry then finds
		# the object the first try made and fails. That mutex is this build's own.
		if [[ $held_gen =~ ^[0-9]+$ ]] && grep -qxF "build_id=$BUILD_ID" <<<"$content"; then
			printf '%s\n' "$held_gen" >"$DEPLOY_STATE_DIR/lock-generation"
			log "acquired $DEPLOY_LOCK_OBJECT (generation $held_gen) for build $BUILD_ID at $COMMIT_SHA; an earlier try of this build's create had made it"
			return 0
		fi

		now=$(date +%s)
		if [[ $held_gen =~ ^[0-9]+$ && $created =~ ^[0-9]+$ ]]; then
			age="$((now - created))s old"
			if ((now - created >= DEPLOY_LOCK_STALE_SECONDS)); then
				log "the mutex (generation $held_gen, $age: ${holder:-holder unreadable}) is past the ${DEPLOY_LOCK_STALE_SECONDS}s stale threshold; presuming its build was killed and breaking it"
				if err=$(gcloud storage rm --if-generation-match="$held_gen" "$DEPLOY_LOCK_OBJECT" 2>&1 >/dev/null); then
					continue
				fi
				# Lost to another waiter or a release, or the delete was refused:
				# either way wait a poll, rather than spin.
				log "could not break it: $err"
			fi
		else
			# An age that cannot be read is never taken for a stale one: the
			# mutex may be live.
			age="of unknown age"
			log "could not read the mutex's generation and age from '$info'; not breaking it"
		fi

		if ((now >= deadline)); then
			die "gave up after ${DEPLOY_LOCK_WAIT_SECONDS}s; the mutex is still held (generation $held_gen, $age: ${holder:-holder unreadable}).
If no build is deploying, clear it by hand: gcloud storage rm $DEPLOY_LOCK_OBJECT"
		fi
		if [[ $held_gen != "$last_logged_gen" ]] || ((polls % 6 == 0)); then
			log "waiting: held by ${holder:-an unreadable holder} (generation $held_gen, $age)"
			last_logged_gen=$held_gen
		fi
		polls=$((polls + 1))
		sleep "$poll"
	done
}

decide() {
	require COMMIT_SHA CLOUD_RUN_SERVICE CLOUD_RUN_REGION GCP_PROJECT DEPLOY_REPO_URL \
		DEPLOY_STATE_DIR
	is_sha "$COMMIT_SHA" || die "COMMIT_SHA must be a full 40-character commit sha, got '$COMMIT_SHA'"
	mkdir -p "$DEPLOY_STATE_DIR"

	local work out image ready created digest_ref tags live_sha="" decision reason
	work=$(mktemp -d)
	# shellcheck disable=SC2064 # expand $work now; it is local to this function
	trap "rm -rf '$work'" EXIT

	if out=$(gcloud run services describe "$CLOUD_RUN_SERVICE" --region "$CLOUD_RUN_REGION" \
		--project "$GCP_PROJECT" \
		--format='value[separator="|"](spec.template.spec.containers[0].image,status.latestReadyRevisionName,status.latestCreatedRevisionName)' \
		2>"$work/describe.err"); then
		# '|', not value()'s tab: read folds adjacent tabs, so an empty field
		# (no ready revision) would shift the next one into its place.
		image="" ready="" created=""
		IFS='|' read -r image ready created <<<"$out" || true
		if [[ -z $ready ]]; then
			log "service $CLOUD_RUN_SERVICE has no revision that became ready; nothing is serving"
		elif [[ $ready == "$created" ]]; then
			# The newest revision is the one serving, so the spec's image is live.
			# Terraform deploys <registry>/<image>:<commit sha>; the tag follows the last ':'.
			live_sha=${image##*:}
			log "live image: ${image:-none} (revision $ready)"
		else
			# The newest revision never became ready. Traffic follows the latest
			# ready revision, so the API still runs an older image than the spec
			# names, and comparing with the spec would skip a build the API has
			# not got. A revision pins its image by digest; the registry says
			# which commit tags carry that digest.
			log "the newest revision $created never became ready; $ready is serving"
			digest_ref=$(gcloud run revisions describe "$ready" --region "$CLOUD_RUN_REGION" \
				--project "$GCP_PROJECT" --format='value(status.imageDigest)') ||
				die "could not read the image of revision $ready"
			[[ $digest_ref == *@sha256:* ]] || die "revision $ready has no image digest ('$digest_ref')"
			tags=$(gcloud artifacts docker tags list "${digest_ref%@*}" \
				--filter="version~${digest_ref##*@}\$" --format='value(tag)' 2>/dev/null) ||
				die "could not list the registry tags of ${digest_ref%@*}"
			tags=$(grep -E '^[0-9a-f]{40}$' <<<"$tags" || true)
			if [[ $(wc -l <<<"$tags") -eq 1 && -n $tags ]]; then
				live_sha=$tags
				log "live image: $digest_ref, tagged $live_sha (revision $ready)"
			else
				log "cannot tell which commit revision $ready runs: its digest carries commit tags '${tags//$'\n'/ }'"
			fi
		fi
	elif grep -q 'Cannot find service' "$work/describe.err"; then
		log "service $CLOUD_RUN_SERVICE does not exist yet in $CLOUD_RUN_REGION"
	else
		# Anything else (permissions, network) means the guard cannot see what is
		# live; deploying blind could roll the API back, so stop.
		cat "$work/describe.err" >&2
		die "could not read the live image of $CLOUD_RUN_SERVICE"
	fi

	if [[ -z $live_sha ]]; then
		decision=apply reason="no live commit is known to compare with"
	elif [[ $live_sha == "$COMMIT_SHA" ]]; then
		decision=apply reason="this commit is already live; re-applying its configuration"
	elif ! is_sha "$live_sha"; then
		decision=apply reason="the live tag '$live_sha' is not a commit sha"
	else
		# Cloned only now, holding the mutex: a clone taken before could miss a
		# commit a newer build deployed meanwhile and mistake it for unknown.
		# A failed clone fails the build rather than guessing.
		git clone --quiet --filter=blob:none --no-checkout "$DEPLOY_REPO_URL" "$work/repo" ||
			die "could not clone $DEPLOY_REPO_URL to compare commits"
		git -C "$work/repo" cat-file -e "$COMMIT_SHA^{commit}" 2>/dev/null ||
			die "this build's commit $COMMIT_SHA is not in $DEPLOY_REPO_URL"
		if ! git -C "$work/repo" cat-file -e "$live_sha^{commit}" 2>/dev/null; then
			decision=apply reason="the live commit $live_sha is not in $DEPLOY_REPO_URL"
		elif git -C "$work/repo" merge-base --is-ancestor "$COMMIT_SHA" "$live_sha"; then
			decision=skip reason="the live commit $live_sha already contains $COMMIT_SHA"
		else
			decision=apply reason="the live commit $live_sha is older than or unrelated to $COMMIT_SHA"
		fi
	fi

	printf '%s\n' "$decision" >"$DEPLOY_STATE_DIR/decision"
	if [[ $decision == skip ]]; then
		log "skip: $reason. A newer build has deployed; this one succeeds without deploying."
	else
		log "apply: $reason"
	fi
}

release() {
	require DEPLOY_LOCK_OBJECT DEPLOY_STATE_DIR
	local gen_file="$DEPLOY_STATE_DIR/lock-generation" gen current err="" attempt
	if [[ ! -s $gen_file ]]; then
		log "this build holds no mutex; nothing to release"
		return 0
	fi
	gen=$(<"$gen_file")
	for attempt in 1 2 3; do
		if err=$(gcloud storage rm --if-generation-match="$gen" "$DEPLOY_LOCK_OBJECT" 2>&1 >/dev/null); then
			rm -f "$gen_file"
			log "released $DEPLOY_LOCK_OBJECT (generation $gen)"
			return 0
		fi
		# The delete failed. Only a mutex that is gone, or is now another
		# generation, is no longer this build's to release; anything unclear
		# (the look failing too) is retried, then fails the build.
		if current=$(gcloud storage objects describe "$DEPLOY_LOCK_OBJECT" \
			--format='value(generation)' 2>&1); then
			if [[ $current != "$gen" ]]; then
				log "the mutex is now generation $current, not this build's $gen (presumably broken as stale); leaving it alone"
				rm -f "$gen_file"
				return 0
			fi
		elif [[ $current == *"not found: 404"* ]]; then
			log "the mutex (generation $gen) is already gone"
			rm -f "$gen_file"
			return 0
		else
			err="$err
$current"
		fi
		log "release attempt $attempt of 3 failed: $err"
		((attempt == 3)) || sleep "${DEPLOY_RETRY_SECONDS:-5}"
	done
	die "could not delete this build's mutex (generation $gen). Later builds will break it once it passes their stale threshold, or clear it by hand: gcloud storage rm $DEPLOY_LOCK_OBJECT"
}

case ${1:-} in
acquire | decide | release) "$1" ;;
*) die "usage: $0 acquire|decide|release" ;;
esac
