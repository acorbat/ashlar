import re
try:
    import pathlib
except ImportError:
    import pathlib2 as pathlib
import numpy as np
import skimage.io
from . import reg


# Classes for reading datasets consisting of TIFF files with a naming pattern.
# The pattern must include an integer series number, and optionally a channel
# name or number.
#
# This code is experimental and probably still has a lot of rough edges.


def format_to_regex(s):
    # Translate a restricted subset of the "format" pattern language to
    # a matching regex with named capture.
    s = s.replace('.', '\.')
    regex = re.sub(r'{([^:}]+):?([^}]*)}', f2r_repl, s)
    return regex

def f2r_repl(m):
    r = '(?P<' + m.group(1) + '>.'
    if re.match(r'^\d+$', m.group(2)):
        r += '{' + m.group(2) + '}'
    else:
        r += '*?'
    r += ')'
    return r


class FileSeriesMetadata(reg.Metadata):

    def __init__(self, path, pattern, overlap, width, height):
        # The pattern argument uses the Python Format String syntax with
        # required "series" and optionally "channel" fields. A width
        # specification with leading zeros must be used for any fields that are
        # zero-padded. The pattern is used both to parse the filenames upon
        # initialization as well as to synthesize filenames when reading images.
        # Example pattern: 'img_s{series}_w{channel}.tif'
        self.path = pathlib.Path(path)
        self.pattern = pattern
        self.overlap = overlap
        self.width = width
        self.height = height
        self._enumerate_tiles()

    def _enumerate_tiles(self):
        regex = format_to_regex(self.pattern)
        series = set()
        channels = set()
        n = 0
        self.filename_components = {}
        for p in self.path.iterdir():
            match = re.match(regex, p.name)
            if match:
                gd = match.groupdict()
                s = int(gd['series'])
                c = gd.get('channel')
                series.add(s)
                channels.add(c)
                self.filename_components[s, c] = gd
                n += 1
        if len(self.filename_components) != len(series) * len(channels):
            raise Exception("Missing images detected")
        self._actual_num_images = len(series)
        self.channel_map = dict(enumerate(sorted(channels)))
        self.series_offset = min(series)
        path = self.path / self.filename(self.series_offset, 0)
        img = skimage.io.imread(str(path))
        self._tile_size = np.array(img.shape[:2])
        self._dtype = img.dtype
        self.multi_channel_tiles = False
        # Handle multi-channel tiles (pattern must not include channel).
        if len(self.channel_map) == 1 and img.ndim == 3:
            self.channel_map = {c: None for c in range(img.shape[2])}
            self.multi_channel_tiles = True
        self._num_channels = len(self.channel_map)

    @property
    def _num_images(self):
        return self._actual_num_images

    @property
    def num_channels(self):
        return self._num_channels

    @property
    def pixel_size(self):
        return 1.0

    @property
    def pixel_dtype(self):
        return self._dtype

    def tile_position(self, i):
        row, col = self.tile_rc(i)
        return [row, col] * self.tile_size(i) * (1 - self.overlap)

    def tile_size(self, i):
        return self._tile_size

    def tile_rc(self, i):
        row = i // self.width
        col = i % self.width
        return row, col

    def filename(self, series, c):
        series = series + self.series_offset
        c = self.channel_map[c]
        components = self.filename_components[series, c]
        return self.pattern.format(**components)


class FileSeriesReader(reg.Reader):

    def __init__(self, path, pattern, overlap, width, height):
        # See FileSeriesMetadata for an explanation of the pattern syntax.
        self.path = pathlib.Path(path)
        self.pattern = pattern
        self.metadata = FileSeriesMetadata(
            self.path, self.pattern, overlap, width, height
        )

    def read(self, series, c):
        path = str(self.path / self.metadata.filename(series, c))
        kwargs = {}
        if self.metadata.multi_channel_tiles:
            kwargs['key'] = c
        return skimage.io.imread(path, **kwargs)
