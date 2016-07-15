#!/usr/bin/env python

__all__ = ['dendrogram', 'dotplot', 'linear', 'colors', 'TrackDefn',
            'Display', 'DisplayPolicy', 'Area', 'Arrow', 'BluntArrow',
            'Box', 'Diamond'] + [
    'arrow_rates', 'dinuc', 'fancy_arrow', 'codon_usage', 'util']

__copyright__ = "Copyright 2007-2012, The Cogent Project"
__contributors__ = ["Peter Maxwell", "Gavin Huttley", "Rob Knight",
                    "Zongzhi Liu", "Matthew Wakefield", "Stephanie Wilson"]
__license__ = "GPL"
__version__ = "1.5.3-dev"
__status__ = "Production"

from cogent3.draw.linear import (colors, TrackDefn, Display, DisplayPolicy,
                                 Area, Arrow, BluntArrow, Box, Diamond)

try:
    import cogent3.draw.matplotlib
except ImportError:
    pass
else:
    import warnings
    warnings.warn("You still have a cogent/draw/matplotlib subpackage" +
                  " present, that will cause problems for matplotlib imports")
