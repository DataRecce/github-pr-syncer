# cli.py
import click
from prsync import GithubPrSyncer

@click.command()
@click.argument('repo_name')
@click.option('--repo-path', default='.', help='Path to the git repository. Default is the current directory.')
def main(repo_name, repo_path):
    syncer = GithubPrSyncer(repo_name, repo_path=repo_path)
    syncer.sync()

if __name__ == '__main__':
    main()
