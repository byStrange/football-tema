#!/usr/bin/env fish
# Iterate over all agent slots, switch to main, and pull latest changes

for slot in tmp-agent-workspace/slot-*
    set -l repo "$slot/football-tema"
    if not test -d "$repo/.git"
        echo "SKIP $slot (no git repo found)"
        continue
    end

    echo "→ Pulling $repo ..."
    pushd "$repo"

    # Switch to main branch
    git checkout main

    # Pull latest changes
    git pull origin main

    popd
end

echo "Done."
