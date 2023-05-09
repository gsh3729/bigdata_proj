import enum
import gzip
import hashlib
import json
import logging
import os
import requests
import sqlite3
import tempfile
import threading
import unicodedata


__version__ = '0.3.1'


logger = logging.getLogger(__name__)


SOURCE = 'https://vida-nyu.gitlab.io/auctus/datamart-geo/info.json'


class Type(enum.Enum):
    ADMIN_0 = 0
    COUNTRY = 0
    ADMIN_1 = 1
    ADMIN_2 = 2
    ADMIN_3 = 3
    ADMIN_4 = 4
    ADMIN_5 = 5


def normalize(string):
    string = string.lower()
    string = unicodedata.normalize('NFC', string)
    return string


def _download(url, destination, sha1):
    sha1_hasher = hashlib.sha1()
    dirname = os.path.dirname(destination)

    # Can't use NamedTemporaryFile because it would try to delete afterwards
    # Doesn't use mkstemp because permissions are too strict
    tmp = tempfile.mktemp(dir=dirname)
    try:
        with open(tmp, 'wb') as fp:
            with requests.get(url, stream=True) as resp:
                resp.raise_for_status()
                for chunk in resp.iter_content(4096):
                    sha1_hasher.update(chunk)
                    fp.write(chunk)

        file_hash = sha1_hasher.hexdigest()
        if file_hash != sha1:
            raise ValueError(
                "Checksum does not match: %s != %s" % (
                    file_hash, sha1),
            )

        # Check for gzip
        with open(tmp, 'rb') as fp:
            magic = fp.read(2)
        if magic == b'\x1F\x8B':
            tmp2 = tempfile.mktemp(dir=dirname)
            try:
                with open(tmp2, 'wb') as dest:
                    with gzip.open(tmp) as src:
                        chunk = src.read(4096)
                        while chunk:
                            dest.write(chunk)
                            if len(chunk) != 4096:
                                break
                            chunk = src.read(4096)
            except BaseException:
                os.remove(tmp2)
                raise
            else:
                os.remove(tmp)
                tmp = tmp2

        os.rename(tmp, destination)
    except BaseException:
        os.remove(tmp)
        raise


class GeoData(object):
    def __init__(self, data_path):
        """Load the data from a local directory.
        """
        self._data_path = os.path.abspath(data_path)
        db_file = os.path.join(self._data_path, 'admins.gpkg')
        if not os.path.exists(db_file):
            raise FileNotFoundError(
                "No local data found; you need to download data before "
                + "using datamart-geo"
            )
        self._thread_local = threading.local()
        self._ngrams = None

    @property
    def _database(self):
        # SQLite3 doesn't allow concurrent access from different threads,
        # so we create a separate connection per thread
        tl = self._thread_local
        try:
            database = tl.database
        except AttributeError:
            database = sqlite3.connect(
                os.path.join(self._data_path, 'admins.gpkg')
            )
            self._thread_local.database = database
        return database

    @staticmethod
    def get_local_cache_path():
        """Get the path to the cache directory.
        """
        if 'DATAMART_GEO_DATA' in os.environ:
            return os.path.expanduser(os.environ['DATAMART_GEO_DATA'])
        elif 'XDG_CACHE_HOME' in os.environ:
            cache = os.environ['XDG_CACHE_HOME']
        else:
            cache = os.path.expanduser('~/.cache')
        return os.path.join(cache, 'datamart-geo')

    @classmethod
    def from_local_cache(cls):
        """Load the data from the cache directory.
        """
        return cls(cls.get_local_cache_path())

    @classmethod
    def download(cls, destination=None, *, source=SOURCE, update=True):
        """Download the data. This needs to be done before use.

        The geo database is open data. Check the documentation for the license
        terms.

        :param destination: Directory where to save the data. If ``None``
            (default) the current user's cache directory will be used.
        :param update: If True (default), a new version will be downloaded if
            available. If False, data will only be downloaded if no version of
            the data is present locally.
        """
        import requests

        if destination is None:
            destination = cls.get_local_cache_path()

        # Hit the website to get the latest file locations
        info = requests.get(source)
        info.raise_for_status()
        info = info.json()

        # Check directory
        if not os.path.exists(destination):
            os.mkdir(destination)
        elif os.path.exists(os.path.join(destination, 'state.json')):
            with open(os.path.join(destination, 'state.json')) as fp:
                state = json.load(fp)
            if state['version'] != 1:
                raise ValueError(
                    "The data directory is from a different version of "
                    "datamart-geo"
                )
            if not update and state['data']:
                logger.info("Data is present, %s", state['data'])
                return cls(destination)
            elif (
                'data' in state
                and state['data']['version'] == info['data']['version']
            ):
                logger.info("Data is up to date, %s", state['data']['version'])
                return cls(destination)
            else:
                # Clear info for now, so a failed download doesn't leave behind
                # a valid state
                os.remove(os.path.join(destination, 'state.json'))

        # Download data
        logger.info("Downloading data to %s...", destination)
        _download(
            info['data']['admins.gpkg']['url'],
            os.path.join(destination, 'admins.gpkg'),
            info['data']['admins.gpkg']['sha1'],
        )
        logger.info("Downloading fuzzy index to %s...", destination)
        _download(
            info['data']['admins.names.trie']['url'],
            os.path.join(destination, 'admins.names.trie'),
            info['data']['admins.names.trie']['sha1'],
        )
        with open(os.path.join(destination, 'state.json'), 'w') as fp:
            json.dump(
                dict(
                    version=1,
                    data=info['data'],
                ),
                fp,
            )
        logger.info("Downloaded data, version %s", info['data']['version'])

        return cls(destination)

    def resolve_name(self, name):
        for area in self.resolve_name_all(name):
            return area
        return None

    def resolve_name_all(self, name):
        cur = self._database.execute(
            '''
            SELECT
                admins.id, name, level, latitude, longitude,
                country, admin1, admin2, admin3, admin4, admin5,
                minx, maxx, miny, maxy
            FROM admins
            LEFT OUTER JOIN rtree_admins_shape
                ON admins.id = rtree_admins_shape.id
            WHERE admins.id IN (SELECT id FROM names WHERE name = ?);
            ''',
            (normalize(name),),
        )
        while True:
            area = self._make_area_from_cursor(cur)
            if area is None:
                break
            yield area

    def _make_area_from_cursor(self, cur):
        for row in cur:
            id, name, level, latitude, longitude = row[:5]
            levels = row[5:11]
            bounds = row[11:15]
            if any(n is None for n in bounds):
                bounds = None
            type = Type(level)
            return Area(
                self, id, name, type, levels,
                latitude, longitude, bounds,
            )
        return None

    def resolve_names(self, names):
        # Might be something faster in the future
        return [self.resolve_name(name) for name in names]

    def resolve_names_all(self, names):
        # Might be something faster in the future
        return [list(self.resolve_name_all(name)) for name in names]

    def resolve_name_fuzzy(self, name, threshold=0.3):
        # Open ngrams database
        if self._ngrams is None:
            import ngram_search
            self._ngrams = ngram_search.Ngrams(
                os.path.join(self._data_path, 'admins.names.trie')
            )

        # Execute fuzzy search with ngrams
        hits = self._ngrams.search(name, threshold)

        # Build results
        results = []
        for name_id, score in hits:
            cur = self._database.execute(
                '''
                SELECT
                    admins.id, name, level, latitude, longitude,
                    country, admin1, admin2, admin3, admin4, admin5,
                    minx, maxx, miny, maxy
                FROM admins
                LEFT OUTER JOIN rtree_admins_shape
                    ON admins.id = rtree_admins_shape.id
                WHERE admins.id = (SELECT id FROM names WHERE name_id = ?);
                ''',
                (name_id,),
            )
            results.append((score, self._make_area_from_cursor(cur)))
        return results

    def resolve_names_fuzzy(self, names):
        # Might be something faster in the future
        return [self.resolve_name_fuzzy(name) for name in names]


class Area(object):
    def __init__(
        self, geodata, id, name, type, levels,
        latitude, longitude, bounds,
    ):
        self._geodata = geodata
        self.id = id
        self.name = name
        self._names = None
        self.type = type
        self.levels = levels
        self.latitude, self.longitude = latitude, longitude
        self.bounds = bounds

    @property
    def names(self):
        if self._names is None:
            cur = self._geodata._database.execute(
                '''
                SELECT name FROM names WHERE id = ?;
                ''',
                (self.id,),
            )
            self._names = {
                row[0]
                for row in cur
            }
            self._names.add(self.name)
        return self._names

    def __repr__(self):
        return '<%s "%s" (%s) type=%s>' % (
            self.__class__.__module__ + '.' + self.__class__.__name__,
            self.name,
            self.id,
            self.type,
        )

    def __eq__(self, other):
        if isinstance(other, Area):
            return self.id == other.id
        return False

    def __ne__(self, other):
        if isinstance(other, Area):
            return self.id != other.id
        return True

    def __hash__(self):
        return hash(self.id)

    def _get_area_from_levels(self, levels):
        field_names = [
            'country', 'admin1', 'admin2',
            'admin3', 'admin4', 'admin5',
        ]
        # Build the where clause: match all levels
        where = ' AND '.join(
            '{field}=?'.format(field=field_names[i])
            for i in range(len(levels))
        )
        cur = self._geodata._database.execute(
            '''
            SELECT
                admins.id, name, level, latitude, longitude,
                country, admin1, admin2, admin3, admin4, admin5,
                minx, maxx, miny, maxy
            FROM admins
            LEFT OUTER JOIN rtree_admins_shape
                ON admins.id = rtree_admins_shape.id
            WHERE level={level} AND {where};
            '''.format(level=len(levels) - 1, where=where),
            levels,
        )
        return self._geodata._make_area_from_cursor(cur)

    def get_parent_area(self, level=None):
        if level is None:
            # No level specified -- use closest parent e.g. highest level
            for level_num in range(5, -1, -1):
                if self.levels[level_num] is None:
                    continue
                if level_num == self.type.value:
                    # This is the current area, skip it
                    continue
                return self._get_area_from_levels(self.levels[:level_num + 1])
        else:
            # Check type
            if isinstance(level, Type):
                level = level.value
            elif not isinstance(level, int):
                raise ValueError(
                    "Invalid level, expected int or Type, got %r" % type(level)
                )

            # Get from levels
            if not 0 <= level <= 5:
                raise ValueError("Invalid level %r" % (level,))
            elif self.levels[level] is not None:
                return self._get_area_from_levels(self.levels[:level + 1])

        return None
