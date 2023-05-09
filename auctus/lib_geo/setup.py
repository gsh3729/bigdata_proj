import io
import os
from setuptools import setup


os.chdir(os.path.abspath(os.path.dirname(__file__)))


with io.open('README.rst', encoding='utf-8') as fp:
    description = fp.read()
setup(name='datamart-geo',
      version='0.3.1',
      packages=['datamart_geo'],
      install_requires=['requests'],
      extras_require={'fuzzy': ['ngram-search']},
      description="Geographical location data",
      author="Remi Rampin",
      author_email='remi.rampin@nyu.edu',
      maintainer="Remi Rampin",
      maintainer_email='remi.rampin@nyu.edu',
      url='https://gitlab.com/ViDA-NYU/auctus/datamart-geo',
      project_urls={
          'Homepage': 'https://gitlab.com/ViDA-NYU/auctus/datamart-geo',
          'Source': 'https://gitlab.com/ViDA-NYU/auctus/datamart-geo',
          'Tracker': 'https://gitlab.com/ViDA-NYU/auctus/datamart-geo'
                     + '/-/issues',
      },
      long_description=description,
      license='BSD-3-Clause',
      keywords=['auctus', 'datamart'],
      classifiers=[
          'Development Status :: 4 - Beta',
          'Intended Audience :: Science/Research',
          'License :: Free for non-commercial use',
          'Natural Language :: English',
          'Operating System :: OS Independent',
          'Programming Language :: Python :: 3 :: Only',
          'Topic :: Database'])
