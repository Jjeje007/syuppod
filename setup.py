# -*- python3 -*- 
# -*- coding: utf-8 -*-

from setuptools import setup

setup(name = 'syuppo',
      version = '0.1',
      description = 'SYnc UPdate Portage.',
      long_description = """Syuppo is a python3 daemon (syuppod) 
      which automate sync and calculate how many packages to update
      for gentoo portage manager. His client (syuppoc) retrieve these informations over dbus.""",
      classifiers = [
            'Development Status :: 4 - Beta',
            'Topic :: Utilities'
            ],
      keywords = '',
      url = 'https://github.com/Jjeje007/syuppod',
      author = 'Venturi Jérôme',
      author_email = 'jerome.venturi@gmail.com',
      license = 'GPL-3.0-or-later',
      packages = ['syuppo'],
      scripts = ['syuppod', 'syuppoc'],
      zip_safe=False)
