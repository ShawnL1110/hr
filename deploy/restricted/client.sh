#!/bin/sh
set -eu
: "${HR_DEPLOY_KEY:?Set HR_DEPLOY_KEY to the dedicated HR private key path}"
: "${HR_DEPLOY_HOST:=35.42.59.31}"
if [ "$#" -ne 1 ]; then echo 'Usage: client.sh status|logs|release' >&2; exit 2; fi
case "$1" in
  status|logs) exec ssh -i "$HR_DEPLOY_KEY" -o IdentitiesOnly=yes "hr-deploy@$HR_DEPLOY_HOST" "$1" ;;
  release)
    test -z "$(git status --porcelain)" || { echo 'Commit changes before release' >&2; exit 2; }
    rev=$(git rev-parse HEAD)
    git archive --format=tar HEAD | ssh -i "$HR_DEPLOY_KEY" -o IdentitiesOnly=yes "hr-deploy@$HR_DEPLOY_HOST" "release $rev"
    ;;
  *) echo 'Unknown command' >&2; exit 2 ;;
esac
