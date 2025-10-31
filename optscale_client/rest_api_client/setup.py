#!/usr/bin/env python
from setuptools import setup


requirements = ["requests==2.32.4", "retrying>=1.4.1"]

setup(name='restapi-client',
      description='OptScale REST API Client',
      url='http://hystax.com',
      author='Hystax',
      author_email='info@hystax.com',
      package_dir={'rest_api_client': ''},
      packages=['rest_api_client'],
      install_requires=requirements,
      )
