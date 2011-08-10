from setuptools import setup, find_packages

setup(
    name='panomena-analytics',
    description='Panomena Analytics',
    version='0.0.1-django-1.2.3-backport.1',
    author='',
    license='Proprietory',
    url='http://www.unomena.com/',
    packages = find_packages('src'),
    package_dir = {'': 'src'},
    dependency_links = [
    ],
    install_requires = [
        'Django==1.2.3',
    ],
)
