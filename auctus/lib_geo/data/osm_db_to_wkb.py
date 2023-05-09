#!/usr/bin/env python3
import asyncio
from concurrent.futures.process import ProcessPoolExecutor
import csv
import logging
import os
from shapely.geometry.polygon import Polygon
import sqlite3
import struct
import sys

from utils import apply_async


logger = logging.getLogger('osm_db_to_wkt')

csv.field_size_limit(sys.maxsize)


class GeoDataError(ValueError):
    """Geo data can't be rebuilt properly"""


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if len(sys.argv) != 2 or not os.path.exists(sys.argv[1]):
        print("usage: osm_db_to_wkt.py <osm-data.sqlite3>", file=sys.stderr)
        sys.exit(2)

    Writer(sys.argv[1], 'polygons.wkt.csv').run()


class Writer(object):
    def __init__(self, input_db_name, output_wkt_name):
        self.input_db_name = input_db_name
        self.output_wkt_name = output_wkt_name

    def run(self):
        self.input_conn = sqlite3.connect(self.input_db_name)
        self.input_conn.execute('PRAGMA cache_size=-1000000;')
        self.input_conn.execute('PRAGMA synchronous=OFF;')

        self.output_conn = sqlite3.connect('admins.gpkg')
        self.output_conn.execute('PRAGMA cache_size=-1000000;')
        self.output_conn.execute('PRAGMA synchronous=OFF;')
        self.output_conn.enable_load_extension(True)
        self.output_conn.load_extension('mod_spatialite')

        # Read mapping of relation ID to geonames ID and name
        self.relation_info = {}
        with open('osm_shapes.csv') as fp:
            reader = csv.reader(fp)
            try:
                assert next(reader) == [
                    'wikidataId', 'geonamesId', 'label', 'osmId',
                ]
            except StopIteration:
                raise AssertionError
            for row in reader:
                self.relation_info.setdefault(row[3], []).append(
                    (int(row[1]), row[2]),
                )

        # List relations from database (that have nodes)
        cursor = self.input_conn.cursor()
        rows = cursor.execute(
            '''
            SELECT DISTINCT relation
            FROM relation_ways
            WHERE EXISTS (
                SELECT way FROM way_nodes WHERE way_nodes.way = relation_ways.way
            );
            ''',
        )
        relations = [r for r, in rows]
        logger.info("Found %d relations", len(relations))

        # For each relation, build a multipolygon shape
        self.success = 0
        with ProcessPoolExecutor() as pool:
            async def process(i, relation):
                logger.info("Reading relation %d/%d: %s",
                            i + 1, len(relations), relation)
                await self.read_relation(pool, relation)

            asyncio.run(apply_async(process, enumerate(relations), max_tasks=8))

        self.output_conn.commit()
        logger.info("Successfully parsed %d/%d relations",
                    self.success, len(relations))

    async def read_relation(self, pool, relation):
        try:
            ways = read_ways(self.input_conn, relation)
            polygons = await asyncio.get_event_loop().run_in_executor(
                pool,
                parse_relation,
                ways,
            )
        except GeoDataError:
            logger.warning("Error processing relation %s", relation,
                           exc_info=True)
            return None

        # Put it in database
        for geoname_id, name in self.relation_info[relation]:
            cursor = self.output_conn.cursor()
            cursor.execute(
                '''
                UPDATE admins
                SET shape=:shape
                WHERE id=:id;
                ''',
                {
                    'id': geoname_id,
                    'shape': multipolygon_binary(polygons, True),
                },
            )

        self.success += 1


def read_ways(conn, relation):
    cursor = conn.cursor()
    rows = cursor.execute(
        '''
        SELECT relation_ways.way, relation_ways.role, node, lat, lon
        FROM relation_ways
        LEFT OUTER JOIN way_nodes ON relation_ways.way = way_nodes.way
        WHERE relation_ways.relation = ?
        ORDER BY relation_ways.idx, way_nodes.idx;
        ''',
        (relation,),
    )
    ways = {}
    current_way = None
    current_role = None
    current_way_points = []
    missing_ways = set()
    missing_nodes = set()
    for way, role, node, lat, lon in rows:
        if node is None:
            missing_ways.add(way)
        elif lat is None:
            missing_nodes.add(node)
        if current_way is None:
            current_way = way
            current_role = role
            current_way_points.append((lat, lon))
        elif current_way == way:
            current_way_points.append((lat, lon))
        else:
            ways[current_way] = current_role, current_way_points
            current_way = way
            current_role = role
            current_way_points = [(lat, lon)]
    ways[current_way] = current_role, current_way_points

    if missing_ways:
        raise GeoDataError("Missing ways: %s" % ', '.join(missing_ways))
    if missing_nodes:
        raise GeoDataError("Missing nodes: %s" % ', '.join(missing_nodes))

    logger.info("Read %d ways", len(ways))
    return ways


def parse_relation(ways):
    unassigned_ways = ways

    # Build an index of ways from their endpoints
    endpoint_index = {}
    for way, (role, way_points) in unassigned_ways.items():
        endpoint_index.setdefault(way_points[0], set()).add(way)
        endpoint_index.setdefault(way_points[-1], set()).add(way)
    logger.info("%d different endpoint locations", len(endpoint_index))

    # https://wiki.openstreetmap.org/wiki/Relation:multipolygon/Algorithm

    # Build rings from ways
    rings = []
    current_ring = current_role = None
    while unassigned_ways:
        if current_ring is None:
            # Start a ring using a random way
            way = next(iter(unassigned_ways))
            current_role, way_points = unassigned_ways.pop(way)
            current_ring = list(way_points)
            logger.debug("NEWRING: %r - %r (%s)",
                         way_points[0], way_points[-1], current_role)

        if current_ring[0] != current_ring[-1]:
            # Get a way which start from our current location
            possibilities = sum(
                1 for way in endpoint_index[current_ring[-1]]
                if unassigned_ways.get(way, [''])[0] == current_role
            )
            if possibilities > 1:
                logger.warning("%d possibilities to continue ring",
                               possibilities)
            for way in endpoint_index[current_ring[-1]]:
                try:
                    role, way_points = unassigned_ways[way]
                except KeyError:
                    pass
                else:
                    if role == current_role:
                        del unassigned_ways[way]
                        break
                    else:
                        logger.debug("WRONGROLE: %r - %r (%s)",
                                     way_points[0], way_points[-1], role)
            else:
                raise GeoDataError("Can't find way to continue building ring")

            # Add it to the ring
            if way_points[0] == current_ring[-1]:
                current_ring.extend(way_points[1:])
            elif way_points[-1] == current_ring[-1]:
                current_ring.extend(way_points[-2::-1])
            else:
                raise AssertionError
            logger.debug("POSITION: %r", current_ring[-1])

        # Check if the ring is closed
        if current_ring[0] == current_ring[-1]:
            logger.debug("RING: closed ring with %d points", len(current_ring))
            rings.append((current_role, current_ring))
            current_ring = None

    if current_ring is not None:
        raise GeoDataError("Unclosed ring")

    logger.info("Built %d rings", len(rings))

    # Build polygons from rings
    _memo = {}

    def _shapely_ring(ring):
        return Polygon([
            (float(lon), float(lat))
            for (lat, lon) in ring
        ])

    def contained(needle, haystack):
        try:
            return _memo[(id(needle), id(haystack))]
        except KeyError:
            needle = _shapely_ring(needle)
            haystack = _shapely_ring(haystack)
            result = haystack.contains(needle)
            _memo[(id(needle), id(haystack))] = result
            return result

    polygons = []
    while rings:
        # Pick an outer ring
        for i, (role, outer_ring) in enumerate(rings):
            if role == 'outer':
                break
        else:
            raise GeoDataError("Only inner rings left")
        del rings[i]
        logger.debug("Got outer ring")

        # Find inner rings
        inner_rings = []
        i = 0
        while i < len(rings):
            role, inner_ring = rings[i]
            if role != 'inner':
                i += 1
                continue

            if not contained(inner_ring, outer_ring):
                i += 1
                continue

            inner_rings.append(inner_ring)
            del rings[i]
            logger.debug("add inner ring")

        # Polygon complete
        polygons.append([outer_ring] + inner_rings)
        logger.debug("Store polygon")

    logger.info("Built %d polygons", len(polygons))

    return polygons


def multipolygon_wkt(polygons):
    multipolygon = ['MULTIPOLYGON (']
    for polygon_num, polygon in enumerate(polygons):
        if polygon_num > 0:
            multipolygon.append(', ')
        multipolygon.append('(')
        for ring_num, ring in enumerate(polygon):
            if ring_num > 0:
                multipolygon.append(', ')
            multipolygon.append('(')
            for point_num, (lat, lon) in enumerate(ring):
                if point_num > 0:
                    multipolygon.append(', ')
                multipolygon.append('%s %s' % (lon, lat))
            multipolygon.append(')')
        multipolygon.append(')')
    multipolygon.append(')')

    return ''.join(multipolygon)


def multipolygon_binary(polygons, geopackage_header=False):
    multipolygon = []

    if geopackage_header:
        multipolygon.extend([
            b'\x47\x50',  # magic
            b'\x00',  # version
        ])
        # flags:
        if not polygons:
            multipolygon.append(bytes([
                (
                    1  # Little endian
                ) | (
                    0  # No envelope
                ) << 1 | (
                    1  # Empty
                ) << 4 | (
                    0  # StandardGeoPackageBinary
                )
            ]))
            multipolygon.append(struct.pack('<i', 4326))
            return b''.join(multipolygon)
        else:
            multipolygon.append(bytes([
                (
                    1  # Little endian
                ) | (
                    1  # Envelope is [minx, maxx, miny, maxy]
                ) << 1 | (
                    0  # Non-empty
                ) << 4 | (
                    0  # StandardGeoPackageBinary
                )
            ]))
            multipolygon.append(struct.pack('<i', 4326))

        # Envelope
        minx = miny = float('INF')
        maxx = maxy = float('-INF')
        for polygon in polygons:
            for ring in polygon:
                for lat, lon in ring:
                    lat = float(lat)
                    lon = float(lon)
                    minx = min(minx, lon)
                    maxx = max(maxx, lon)
                    miny = min(miny, lat)
                    maxy = min(maxy, lat)
        multipolygon.append(struct.pack(
            '<dddd',
            minx, maxx, miny, maxy,
        ))

    # WKB
    multipolygon.append(struct.pack(
        '<BII',
        1,  # Little endian
        6,  # Type = 2D multipolygon
        len(polygons),  # Number of polygons
    ))

    for polygon in polygons:
        multipolygon.append(struct.pack(
            '<BII',
            1,  # Little endian
            3,  # Type = 2D polygon
            len(polygon),  # Number of rings
        ))
        for ring in polygon:
            multipolygon.append(struct.pack(
                '<I',
                len(ring),  # Number of points
            ))
            for lat, lon in ring:
                lat = float(lat)
                lon = float(lon)
                multipolygon.append(struct.pack(
                    '<dd',
                    lon,
                    lat,
                ))

    return b''.join(multipolygon)


if __name__ == '__main__':
    main()
