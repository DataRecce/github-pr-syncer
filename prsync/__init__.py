import os
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
        self.github = Github(os.getenv('GITHUB_TOKEN'))
        if self.github is None:
            raise ValueError('GITHUB_TOKEN is required')

        self.github_repo = self.github.get_repo(github_repo)
        if not self.github_repo.fork:
            raise ValueError(f'{github_repo} is not a fork')
        self.local_repo = git.Repo(repo_path)
        self.remote_name = 'origin'
        self.remote_parent_name = self.github_repo.owner.login
        self.repo_path = repo_path

    # def get_open_pull_requests(self, repository):
    #     return repository.get_pulls(state='open')

    # def sync_default_branch(self):
    #     branch = self.github_repo.parent.default_branch
    #     self.local_repo.git.push(self.remote_name, f'refs/remotes/{self.remote_parent_name}/{branch}:refs/heads/{branch}', force=True)

    # def fetch_remotes(self):
    #     print(f"Fetching {self.remote_name}...")
    #     self.local_repo.remotes[self.remote_name].fetch()
    #     print(f"Fetching {self.remote_parent_name}...")
    #     self.local_repo.remotes[self.remote_parent_name].fetch()

    def sync_pull_request(self, pr: PullRequest, prsync_dir):
        # format {owner}:{branch_name}
        pr_from = f"{pr.head.user.login}:{pr.head.ref}"
        pr_to = f"{pr.base.user.login}:{pr.base.ref}"
        print(f"Syncing PR #{pr.number}: {pr.title}")
        print(f"from {pr_from} to {pr_to}")

        # Remote details
        repo_name = self.github_repo.name
        owner_name = pr.head.user.login
        remote_name = f'remote_{owner_name}'
        remote_url = f'https://github.com/{owner_name}/{repo_name}.git'

        # Check if the remote already exists, if not, add it
        if remote_name not in [remote.name for remote in self.local_repo.remotes]:
            print(f"Adding remote: {remote_name}")
            self.local_repo.create_remote(remote_name, remote_url)

        # Fetch the branch from the remote
        print(f"Fetch github repo: {owner_name}/{repo_name}")
        self.local_repo.remotes[remote_name].fetch()

        # Create and checkout a local branch
        branch_name = f'{owner_name}/{pr.head.ref}'
        if branch_name not in self.local_repo.heads:
            print(f"Creating local branch: {branch_name}")
            self.local_repo.create_head(branch_name, f'{remote_name}/{pr.head.ref}')
            self.local_repo.git.checkout(branch_name)
        else:
            print(f"Branch {branch_name} already exists. Force to use the latest changes.")
            self.local_repo.git.checkout(branch_name)
            self.local_repo.git.reset('--hard', f'{self.remote_name}/{branch_name}')

        # Check the behind and ahead commits
        behind, ahead = self.local_repo.git.rev_list(f'{remote_name}/{pr.head.ref}...{branch_name}', '--left-right', '--count').split()
        print(f"Branch {branch_name} is {behind} behind and {ahead} ahead. Syncing...")

        # Copy all files in '.githubprsyncer/*' to the root of the repo and commit
        if prsync_dir:
            print(f"Copying files from {prsync_dir}/ to the root of the {self.repo_path}/")
            os.system(f'cp -r {prsync_dir}/* {self.repo_path}/')
            self.local_repo.git.add('.')
            # commit if there are changes
            if self.local_repo.is_dirty():
                self.local_repo.git.commit('-m', f"Auto-sync by GithubPrSyncer")
            else:
                print("No changes to commit. Skip committing.")

        # Push the branch to the remote
        print(f"Pushing branch {branch_name} to remote...")
        self.local_repo.git.push(self.remote_name, branch_name, force=True)

        # Create pull request
        pulls = self.github_repo.get_pulls(state='open', head=f"{self.github_repo.owner.login}:{branch_name}")
        if pulls.totalCount > 0:
            print(f"PR: {pulls[0].html_url}")
            pull_request = pulls[0]
        else:
            body = f"{pr.body}\n\nsynced from `{pr.html_url}`"
            pull_request = self.github_repo.create_pull(title=f'[PRSync] {pr.title}', body=body, head=f"{branch_name}", base=self.github_repo.parent.default_branch)
            print(f"New PR created: {pull_request.html_url}")
        pull_request.set_labels('prsync')

        return pull_request

    def sync(self):
        # get the current branch
        current_branch = self.local_repo.active_branch

        # create temp folder by python library
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                path = os.path.join(self.repo_path, GITHUB_PR_SYNCER_DIR)
                prsycn_dir = None
                if os.path.exists(path):
                    # copy the files from .githubprsyncer/* to the temp dir
                    print(f"Copying files from {GITHUB_PR_SYNCER_DIR}/* to {temp_dir}/")
                    os.system(f'cp -r {path}/* {temp_dir}/')
                    prsycn_dir = temp_dir
                    print()

                # sync the pull requests
                open_pull_requests = self.github_repo.parent.get_pulls(state='open')
                for pr in open_pull_requests:
                    if pr.number != 1144:
                        continue

                    self.sync_pull_request(pr, prsycn_dir)
                    print()

            finally:
                # checkout back to the original branch
                self.local_repo.git.checkout(current_branch)
        
