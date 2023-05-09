#!/usr/bin/env python3
import bz2
import csv
import gzip
import logging
import os
import sqlite3
import sys
import xml.sax


logger = logging.getLogger('import_osm')


class BaseReader(xml.sax.handler.ContentHandler):
    BUF_SIZE = 16384
    PREFIX = ''

    byte_position = 0
    line_position = 1
    parser = None

    def parse(self, file):
        self.parser = xml.sax.make_parser()
        self.parser.setContentHandler(self)

        file.seek(0, 2)
        total_size = file.tell()
        file.seek(0, 0)
        buf = file.read(self.BUF_SIZE)
        while buf:
            self.parser.feed(buf)
            if len(buf) != self.BUF_SIZE:
                break
            self.byte_position += len(buf)
            self.line_position += buf.count(b'\n')
            if self.byte_position % (self.BUF_SIZE * 1024) == 0:
                logger.info(
                    "%s%d MiB / %d MiB",
                    self.PREFIX,
                    self.byte_position // 1048576,
                    total_size // 1048576,
                )
            buf = file.read(self.BUF_SIZE)

        return self.result()

    def parse_range(self, file, bytes_range):
        self.parser = xml.sax.make_parser()
        self.parser.setContentHandler(self)

        total_size = bytes_range[1][0] - bytes_range[0][0] + self.BUF_SIZE

        # Seek to byte offset
        file.seek(bytes_range[0][0], 0)
        self.byte_position = bytes_range[0][0]

        # Skip lines
        buf = file.read(self.BUF_SIZE)
        for _ in range(bytes_range[0][1]):
            buf = buf[buf.index(b'\n') + 1:]

        self.parser.feed(b'<?xml version="1.0" encoding="UTF-8"?>\n<osm>\n')
        self.parser.feed(buf)
        buf = file.read(self.BUF_SIZE)
        while buf and self.byte_position <= bytes_range[1][0]:
            self.parser.feed(buf)
            if len(buf) != self.BUF_SIZE:
                break
            self.byte_position += len(buf)
            self.line_position += buf.count(b'\n')
            if self.byte_position % (self.BUF_SIZE * 1024) == 0:
                logger.info(
                    "%s%d MiB / %d MiB",
                    self.PREFIX,
                    (self.byte_position - bytes_range[0][0]) // 1048576,
                    total_size // 1048576,
                )
            buf = file.read(self.BUF_SIZE)

        return self.result()

    def get_position(self):
        return (
            # Byte offset of start of buffer
            self.byte_position,
            # Line number inside the buffer
            self.parser.getLineNumber() - self.line_position,
        )

    def result(self):
        return None


class RelationsReader(BaseReader):
    PREFIX = 'relations: '

    def __init__(self, target_relations, cursor):
        super(RelationsReader, self).__init__()
        self.level = 0
        self.target_relations = target_relations
        self.cursor = cursor
        self.relation = None
        self.relation_ways = {}
        self.ways_range = [None, None]
        self.nodes_range = [None, None]

    def startElement(self, name, attrs):
        self.level += 1
        if self.level == 2:
            if name == 'relation':
                if attrs['id'] in self.target_relations:
                    logger.info("Found relation %s", attrs['id'])
                    self.relation = attrs['id']
            elif name == 'way':
                if self.ways_range[0] is None:
                    self.ways_range[0] = self.get_position()
            elif name == 'node':
                if self.nodes_range[0] is None:
                    self.nodes_range[0] = self.get_position()
        elif (
            self.level == 3
            and self.relation is not None
            and name == 'member'
        ):
            if attrs['type'] == 'way' and attrs['role'] in ('inner', 'outer'):
                self.relation_ways.setdefault(self.relation, []).append(
                    (attrs['role'], attrs['ref'])
                )

    def endElement(self, name):
        self.level -= 1
        if self.level == 1:
            if self.relation is not None:
                self.cursor.execute(
                    'DELETE FROM relation_ways WHERE relation = ?;',
                    (self.relation,),
                )
                self.cursor.executemany(
                    '''
                    INSERT INTO relation_ways(relation, idx, role, way)
                    VALUES(?, ?, ?, ?);
                    ''',
                    [
                        (
                            self.relation,
                            idx,
                            role,
                            way,
                        )
                        for idx, (role, way) in enumerate(
                            self.relation_ways.get(self.relation, [])
                        )
                    ]
                )
                self.relation = None
            elif name == 'way':
                self.ways_range[1] = self.get_position()
            elif name == 'node':
                self.nodes_range[1] = self.get_position()

    def result(self):
        return self.relation_ways, self.ways_range, self.nodes_range


class WaysReader(BaseReader):
    PREFIX = 'ways: '

    def __init__(self, target_ways, cursor):
        super(WaysReader, self).__init__()
        self.level = 0
        self.target_ways = target_ways
        self.cursor = cursor
        self.way = None
        self.nodes = []
        self.ways_found = 0

    def startElement(self, name, attrs):
        self.level += 1
        if self.level == 2 and name == 'way':
            if attrs['id'] in self.target_ways:
                logger.info("Found way %s", attrs['id'])
                self.way = attrs['id']
                self.ways_found += 1
        elif self.level == 3 and self.way is not None:
            if name == 'nd':
                self.nodes.append(
                    (True, attrs['ref'])
                )
            elif name == 'node':
                self.nodes.append(
                    (False, (attrs['lat'], attrs['lon']))
                )

    def endElement(self, name):
        self.level -= 1
        if self.level == 1 and self.way is not None:
            self.cursor.execute(
                'DELETE FROM way_nodes WHERE way = ?;',
                (self.way,),
            )
            for idx, (is_ref, v) in enumerate(self.nodes):
                if is_ref:
                    self.cursor.execute(
                        '''
                        INSERT INTO way_nodes(way, idx, node)
                        VALUES(?, ?, ?);
                        ''',
                        (self.way, idx, v),
                    )
                else:
                    self.cursor.execute(
                        '''
                        INSERT INTO way_nodes(way, idx, lat, lon)
                        VALUES(?, ?, ?, ?);
                        ''',
                        (self.way, idx, v[0], v[1]),
                    )
            self.way = None
            self.nodes = []

    def result(self):
        return self.ways_found


class NodesReader(BaseReader):
    PREFIX = 'nodes: '

    def __init__(self, cursor):
        super(NodesReader, self).__init__()
        self.level = 0
        self.cursor = cursor
        self.nodes_found = 0

    def startElement(self, name, attrs):
        self.level += 1
        if self.level == 2 and name == 'node':
            self.cursor.execute(
                '''
                UPDATE way_nodes SET lat = ?, lon = ? WHERE node = ?;
                ''',
                (attrs['lat'], attrs['lon'], attrs['id']),
            )
            if self.cursor.rowcount > 0:
                self.nodes_found += 1

    def endElement(self, name):
        self.level -= 1

    def result(self):
        return self.nodes_found


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if len(sys.argv) != 3:
        print("usage: import_osm.py <osm-data.xml> <output.sqlite3>",
              file=sys.stderr)
        sys.exit(2)

    with open(sys.argv[1], 'rb') as fp:
        magic = fp.read(3)
    if magic[:2] == b'\x1F\x8B':
        input_file = gzip.open(sys.argv[1], 'rb')
    elif magic == b'BZh':
        input_file = bz2.open(sys.argv[1], 'rb')
    else:
        input_file = open(sys.argv[1], 'rb')

    create_tables = not os.path.exists(sys.argv[2])
    conn = sqlite3.connect(sys.argv[2])
    conn.execute('PRAGMA cache_size=-1000000;')
    conn.execute('PRAGMA synchronous=OFF;')
    if create_tables:
        logger.info("Creating tables")
        conn.executescript(
            '''
            CREATE TABLE relation_ways(
                relation TEXT NOT NULL,
                idx INTEGER NOT NULL,
                role TEXT NULL,
                way TEXT NOT NULL
            );
            CREATE INDEX idx_relation_ways_relation ON relation_ways(relation);
            CREATE INDEX idx_relation_ways_way ON relation_ways(way);
            '''
            + '''
            CREATE TABLE way_nodes(
                way TEXT NOT NULL,
                idx INTEGER NOT NULL,
                node TEXT NULL,
                lat TEXT NULL,
                lon TEXT NULL
            );
            CREATE INDEX idx_way_nodes_way ON way_nodes(way);
            CREATE INDEX idx_way_nodes_node ON way_nodes(node);
            ''',
        )

    csv.field_size_limit(sys.maxsize)

    # Read required relations in memory
    relations = set()
    with open('osm_shapes.csv') as fin:
        reader = csv.reader(fin)
        try:
            assert next(reader) == [
                'wikidataId', 'geonamesId', 'label', 'osmId',
            ]
        except StopIteration:
            raise AssertionError
        for row in reader:
            relations.add(row[3])
    logger.info("Looking for %d relations", len(relations))

    # Get required ways for those relations
    cursor = conn.cursor()
    (
        relation_ways,
        ways_range,
        nodes_range,
    ) = RelationsReader(relations, cursor).parse(input_file)
    conn.commit()
    logger.info("Found %d relations", len(relation_ways))

    all_ways = set(w for lw in relation_ways.values() for r, w in lw)
    logger.info("Looking for %d ways", len(all_ways))

    # Get required nodes for those ways
    cursor = conn.cursor()
    count = WaysReader(all_ways, cursor).parse_range(input_file, ways_range)
    conn.commit()
    logger.info("Found %d ways", count)

    # Read the nodes
    cursor = conn.cursor()
    count = NodesReader(cursor).parse_range(input_file, nodes_range)
    conn.commit()
    logger.info("Found %d nodes", count)


if __name__ == '__main__':
    main()
