from setuptools import setup

# setup.py for non-frozen builds

setup(
    name='pros-cli',
    version=open('pip_version').read().strip(),
    packages=['prosflasher', 'proscli', 'prosconfig', 'prosconductor', 'prosconductor.providers'],
    url='https://github.com/purduesigbots/pros-cli',
    license='MPL-2.0',
    author='Purdue ACM SIGBots',
    author_email='pros_development@cs.purdue.edu',
    description='Command Line Interface for managing PROS projects',
    install_requires=[
        'click',
        'pyserial',
        'cachetools',
        'requests',
        'tabulate',
        'jsonpickle',
        'semantic_version'
    ],
    entry_points="""
        [console_scripts]
        pros=proscli.main:main
        """
)
