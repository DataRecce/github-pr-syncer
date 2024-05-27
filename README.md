# github-pr-syncer
Sync all the PRs from the upstream repo.

# Features
1. Sync all the PRs from upstream
2. Support PRs from other forked repo
3. Append additional files to the synced PRs

# Usage

1. Install github-pr-syncer

    ```
    pip install git+https://github.com/DataRecce/github-pr-syncer.git
    ```

2. Run prsync
    ```
    export GITHUB_TOKEN=<GITHUB_TOKEN>
    prsync --repo-path /tmp/oso 'DataRecce/oso'
    ```

# Copy files in `.githubprsync` to synced

Because the synced PR would use the commit from the upstream repo. If we want to add additional files to synced, you can put files in the folder `.githubprsync`. After pr is sycned, the sycner would add files under `.githubprsync` and push a new commit.



