#!/usr/bin/env python3
"""Import missing public-source artwork, or refresh an explicitly selected ID."""
import runpy
if __name__ == '__main__':
    runpy.run_module('app.public_artwork', run_name='__main__')
