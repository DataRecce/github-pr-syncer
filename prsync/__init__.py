import os
import shutil
import tempfile

from github import Github, PullRequest
import git

GITHUB_PR_SYNCER_DIR = '.githubprsyncer'

class GithubPrSyncer:

    def __init__(
        self,
        github_repo,
        repo_path,
    ):
        github_token = os.getenv('GITHUB_TOKEN')
        if github_token is None:
            raise ValueError('GITHUB_TOKEN is required')

        self.github = Github(github_token)
        self.github_repo = self.github.get_repo(github_repo)
        if not self.github_repo.fork:
            raise ValueError(f'{github_repo} is not a fork')
        self.local_repo = git.Repo(repo_path)
        self.remote_name = 'origin'
        self.repo_path = repo_path

    def fetch_origin(self):
        print("Fetching origin...")
        self.local_repo.remotes[self.remote_name].fetch()

    def checkout_and_reset_branch(self, owner_name, branch, synced_branch=None):
        """
        Checkout a branch and sync with the remote
        """
        repo_name = self.github_repo.name

        if owner_name == self.github_repo.owner.login:
            raise ValueError(f'{owner_name} is the same as the owner of the forked repository')

        if synced_branch is None:
            synced_branch = f'{owner_name}/{branch}'

        # Fetch the remote
        remote_name = f'remote_{owner_name}'
        remote_url = f'https://github.com/{owner_name}/{repo_name}.git'
        if remote_name not in [remote.name for remote in self.local_repo.remotes]:
            print(f"Adding remote: {remote_name}")
            self.local_repo.create_remote(remote_name, remote_url)
        print(f"Fetching remote {remote_name}...")
        self.local_repo.remotes[remote_name].fetch()

        # Check if the branch exists, if not, create it
        remote_branch = f'{remote_name}/{branch}'
        print(f"Checkout branch {synced_branch} from {remote_branch}")
        if synced_branch not in self.local_repo.heads:
            self.local_repo.create_head(synced_branch, f'{remote_name}/{branch}')
            self.local_repo.git.checkout(synced_branch)
        else:
            self.local_repo.git.checkout(synced_branch)
            self.local_repo.git.reset('--hard', remote_branch)
        return synced_branch

    def sync_default_branch(self):
        parent_owner = self.github_repo.parent.owner.login
        parant_default_branch = self.github_repo.parent.default_branch
        self.checkout_and_reset_branch(parent_owner, parant_default_branch, parant_default_branch)
        self.local_repo.git.push(self.remote_name, parant_default_branch, force=True)
        print(f"Pushing branch {parant_default_branch} to remote...")
        print()

    def sync_pull_request(self, pr: PullRequest, prsync_dir):
        # Checkout the latest commit of the owner branch
        synced_branch = self.checkout_and_reset_branch(pr.head.user.login, pr.head.ref)

        # Check the behind and ahead commits
        push = False
        remote_branches = [branch.name for branch in self.local_repo.remote().refs]
        if f'{self.remote_name}/{synced_branch}' in remote_branches:
            remote_name = f'remote_{pr.head.user.login}'
            behind, ahead = self.local_repo.git.rev_list(f'{remote_name}/{pr.head.ref}...{self.remote_name}/{synced_branch}', '--left-right', '--count').split()
            print(f"Branch {synced_branch} is {behind} behind and {ahead} ahead.")
            if behind == '0':
                # up-to-date. checkout synced branch from the remote
                self.local_repo.git.reset('--hard', f'{self.remote_name}/{synced_branch}')
            else:
                push = True
        else:
            push = True

        # Copy all files in '.githubprsyncer/' to the root of the repo and commit
        if prsync_dir:
            print(f"Copying files from {prsync_dir}/ to the root of the {self.repo_path}/")
            shutil.copytree(prsync_dir, self.repo_path, dirs_exist_ok=True)

            # commit if there are changes
            self.local_repo.git.add('.')
            if self.local_repo.is_dirty():
                print("New commit")
                self.local_repo.git.commit('-m', f"Auto-sync by GithubPrSyncer")
                push = True
            else:
                print("No changes to commit. Skip committing.")

        # Push the branch to the remote
        if push:
            print(f"Pushing branch {synced_branch} to remote...")
            self.local_repo.git.push(self.remote_name, synced_branch, force=True)

        # Create pull request
        pulls = self.github_repo.get_pulls(state='open', head=f"{self.github_repo.owner.login}:{synced_branch}")
        if pulls.totalCount > 0:
            print(f"PR: {pulls[0].html_url}")
            synced_pr = pulls[0]
        else:
            if pr.body is None:
                body = f"synced from `{pr.html_url}`"
            else:
                body = f"{pr.body}\n\nsynced from `{pr.html_url}`"
            synced_pr = self.github_repo.create_pull(title=f'[PRSync] {pr.title}', body=body, head=f"{synced_branch}", base=self.github_repo.parent.default_branch)
            print(f"New PR created: {synced_pr.html_url}")
        synced_pr.set_labels('prsync')

        return synced_pr

    def sync(self):
        # get the current branch
        current_branch = None
        try:
            current_branch = self.local_repo.active_branch
        except TypeError:
            pass

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                path = os.path.join(self.repo_path, GITHUB_PR_SYNCER_DIR)
                prsycn_dir = None
                if os.path.exists(path):
                    # copy the files from .githubprsyncer/ to the temp dir
                    print(f"Copying files from {path}/ to {temp_dir}/")
                    shutil.copytree(path, temp_dir, dirs_exist_ok=True)
                    prsycn_dir = temp_dir
                    print()

                # sync the default branches
                self.fetch_origin()
                self.sync_default_branch()

                # sync the pull requests
                open_pull_requests = self.github_repo.parent.get_pulls(state='open')
                upstream_open_branches = []
                for pr in open_pull_requests:
                    print(f"Syncing PR: {pr.html_url}")
                    branch_name = f'{pr.head.user.login}/{pr.head.ref}'
                    upstream_open_branches.append(branch_name)
                    self.sync_pull_request(pr, prsycn_dir)
                    print()


                # remove the pr not in synced PRs
                prysync_prs = [pr for pr in self.github_repo.get_pulls(state='open') if 'prsync' in [label.name for label in pr.labels]]
                for pr in prysync_prs:
                    if pr.head.ref not in upstream_open_branches:
                        print(f"Remove PR: {pr.head.ref} at {pr.html_url}")
                        pr.edit(state='closed')
        finally:
            if current_branch:
                self.local_repo.git.checkout(current_branch)
        
