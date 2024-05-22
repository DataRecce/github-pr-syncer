from setuptools import setup, find_packages

setup(
    name='prsync',
    version='0.1.0',
    packages=find_packages(),
    install_requires=[
        'click',
        'GitPython',
        'PyGithub',
    ],
    entry_points={
        'console_scripts': [
            'prsync=prsync.cli:main',  # 'prsync' 是命令名，'prsync.cli:main' 是入口點
        ],
    },
)
