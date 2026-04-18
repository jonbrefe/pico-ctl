#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Jonathan Brenes
from setuptools import setup, find_packages

setup(
    name='pico-ctl',
    version='0.2.1',
    description='All-in-one CLI for managing a Raspberry Pi Pico over USB serial',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    author='Jonathan Brenes',
    url='https://github.com/jonbrefe/pico-ctl',
    license='MIT',
    py_modules=['pico_ctl', 'pico_serial'],
    python_requires='>=3.8',
    install_requires=['pyserial>=3.5'],
    data_files=[('share/man/man1', ['pico_ctl.1'])],
    entry_points={
        'console_scripts': [
            'pico_ctl=pico_ctl:main',
        ],
    },
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3',
        'Topic :: Software Development :: Embedded Systems',
    ],
)
