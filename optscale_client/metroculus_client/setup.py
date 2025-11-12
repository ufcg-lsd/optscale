#!/usr/bin/env python
from setuptools import setup


requirements = ["requests==2.32.4", "retrying==1.4.1"]

setup(name='metroculus-client',
      description='Hystax Metroculus Client',
      url='http://hystax.com',
      author='Hystax',
      author_email='info@hystax.com',
      package_dir={'metroculus_client': ''},
      packages=['metroculus_client'],
      install_requires=requirements,
      )
