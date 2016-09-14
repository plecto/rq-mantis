from setuptools import setup

setup(
    name='rq_mantis',
    version='0.1',
    description='A dashboard for rq',
    url='http://github.com/plecto/rq-mantis',
    author='Plecto ApS',
    license='MIT',
    packages=['rq_mantis'],
    install_requires=[
        'rq',
        'flask',
    ],
    entry_points={
        'console_scripts': ['rq-mantis=rq_mantis.cmd:run']
    },
    zip_safe=False
)
