#!/usr/bin/env fish
# Iterate over all agent slots and push any local commits to their remote branches

for slot in tmp-agent-workspace/slot-*
    set -l repo "$slot/football-tema"
    if not test -d "$repo/.git"
        echo "SKIP $slot (no git repo found)"
        continue
    end

    echo "→ Pushing $repo ..."
    pushd "$repo"

    # Push current branch
    set -l branch (git rev-parse --abbrev-ref HEAD)
    if test "$branch" = "HEAD"
        echo "  WARN: detached HEAD, skipping"
    else
        git push -u origin "$branch"
    end

    popd
end

echo "Done."
