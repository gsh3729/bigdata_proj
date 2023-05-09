PRAGMA foreign_keys=OFF;
PRAGMA application_id(0x47504B47);
PRAGMA user_version(10200);
BEGIN TRANSACTION;

-- http://www.geopackage.org/spec/

-- General GeoPackage stuff
CREATE TABLE gpkg_spatial_ref_sys (srs_name TEXT NOT NULL,srs_id INTEGER NOT NULL PRIMARY KEY,organization TEXT NOT NULL,organization_coordsys_id INTEGER NOT NULL,definition  TEXT NOT NULL,description TEXT);
INSERT INTO gpkg_spatial_ref_sys VALUES('Undefined cartesian SRS',-1,'NONE',-1,'undefined','undefined cartesian coordinate reference system');
INSERT INTO gpkg_spatial_ref_sys VALUES('Undefined geographic SRS',0,'NONE',0,'undefined','undefined geographic coordinate reference system');
INSERT INTO gpkg_spatial_ref_sys VALUES('WGS 84 geodetic',4326,'EPSG',4326,'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563,AUTHORITY["EPSG","7030"]],AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],AXIS["Latitude",NORTH],AXIS["Longitude",EAST],AUTHORITY["EPSG","4326"]]','longitude/latitude coordinates in decimal degrees on the WGS 84 spheroid');
CREATE TABLE gpkg_contents (table_name TEXT NOT NULL PRIMARY KEY,data_type TEXT NOT NULL,identifier TEXT UNIQUE,description TEXT DEFAULT '',last_change DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),min_x DOUBLE, min_y DOUBLE,max_x DOUBLE, max_y DOUBLE,srs_id INTEGER,CONSTRAINT fk_gc_r_srs_id FOREIGN KEY (srs_id) REFERENCES gpkg_spatial_ref_sys(srs_id));
CREATE TABLE gpkg_geometry_columns (table_name TEXT NOT NULL,column_name TEXT NOT NULL,geometry_type_name TEXT NOT NULL,srs_id INTEGER NOT NULL,z TINYINT NOT NULL,m TINYINT NOT NULL,CONSTRAINT pk_geom_cols PRIMARY KEY (table_name, column_name),CONSTRAINT uk_gc_table_name UNIQUE (table_name),CONSTRAINT fk_gc_tn FOREIGN KEY (table_name) REFERENCES gpkg_contents(table_name),CONSTRAINT fk_gc_srs FOREIGN KEY (srs_id) REFERENCES gpkg_spatial_ref_sys (srs_id));
CREATE TABLE gpkg_ogr_contents(table_name TEXT NOT NULL PRIMARY KEY,feature_count INTEGER DEFAULT NULL);
CREATE TABLE gpkg_tile_matrix_set (table_name TEXT NOT NULL PRIMARY KEY,srs_id INTEGER NOT NULL,min_x DOUBLE NOT NULL,min_y DOUBLE NOT NULL,max_x DOUBLE NOT NULL,max_y DOUBLE NOT NULL,CONSTRAINT fk_gtms_table_name FOREIGN KEY (table_name) REFERENCES gpkg_contents(table_name),CONSTRAINT fk_gtms_srs FOREIGN KEY (srs_id) REFERENCES gpkg_spatial_ref_sys (srs_id));
CREATE TABLE gpkg_tile_matrix (table_name TEXT NOT NULL,zoom_level INTEGER NOT NULL,matrix_width INTEGER NOT NULL,matrix_height INTEGER NOT NULL,tile_width INTEGER NOT NULL,tile_height INTEGER NOT NULL,pixel_x_size DOUBLE NOT NULL,pixel_y_size DOUBLE NOT NULL,CONSTRAINT pk_ttm PRIMARY KEY (table_name, zoom_level),CONSTRAINT fk_tmm_table_name FOREIGN KEY (table_name) REFERENCES gpkg_contents(table_name));
CREATE TABLE gpkg_extensions (table_name TEXT,column_name TEXT,extension_name TEXT NOT NULL,definition TEXT NOT NULL,scope TEXT NOT NULL,CONSTRAINT ge_tce UNIQUE (table_name, column_name, extension_name));

-- 'admins' table
CREATE TABLE admins(
    id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    name TEXT NOT NULL CHECK (name <> ''),
    latitude REAL NULL,
    longitude REAL NULL,
    shape MULTIPOLYGON NULL CHECK (length(shape) > 0),
    level INTEGER NOT NULL,
    continent CHAR(2) NULL CHECK (continent <> ''),
    country TEXT NOT NULL CHECK (country <> ''),
    admin1 TEXT NULL CHECK (admin1 <> ''),
    admin2 TEXT NULL CHECK (admin2 <> ''),
    admin3 TEXT NULL CHECK (admin3 <> ''),
    admin4 TEXT NULL CHECK (admin4 <> ''),
    admin5 TEXT NULL CHECK (admin5 <> '')
);
-- rtree
CREATE VIRTUAL TABLE rtree_admins_shape USING rtree(id, minx, maxx, miny, maxy);
-- metadata
INSERT INTO gpkg_contents VALUES('admins','features','admins','','2021-05-11T22:42:26.377Z',NULL,NULL,NULL,NULL,4326);
INSERT INTO gpkg_ogr_contents VALUES('admins',0);
INSERT INTO gpkg_geometry_columns VALUES('admins','shape','MULTIPOLYGON',4326,0,0);
INSERT INTO gpkg_extensions VALUES('admins','shape','gpkg_rtree_index','http://www.geopackage.org/spec120/#extension_rtree','write-only');
-- indexes
CREATE INDEX idx_admins_name ON admins(name);
CREATE INDEX idx_admins_level ON admins(level);
CREATE INDEX idx_admins_continent ON admins(continent);
CREATE INDEX idx_places_country ON admins(country);
CREATE INDEX idx_admins_admin1 ON admins(admin1);
CREATE INDEX idx_admins_admin2 ON admins(admin2);
CREATE INDEX idx_admins_admin3 ON admins(admin3);
CREATE INDEX idx_admins_admin4 ON admins(admin4);
CREATE INDEX idx_admins_admin5 ON admins(admin5);

-- 'names' table
CREATE TABLE names(
    name_id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    id INTEGER NOT NULL,
    name TEXT NOT NULL CHECK (name <> '')
);
-- metadata
INSERT INTO gpkg_contents VALUES('names','attributes','names','','2021-05-11T22:45:26.779Z',NULL,NULL,NULL,NULL,0);
INSERT INTO gpkg_ogr_contents VALUES('names',0);
-- indexes
CREATE INDEX idx_names_id ON names(id);
CREATE INDEX idx_names_name ON names(name);

-- GeoPackage triggers
CREATE TRIGGER gpkg_tile_matrix_zoom_level_insert BEFORE INSERT ON gpkg_tile_matrix FOR EACH ROW BEGIN SELECT RAISE(ABORT, 'insert on table ''gpkg_tile_matrix'' violates constraint: zoom_level cannot be less than 0') WHERE (NEW.zoom_level < 0); END;
CREATE TRIGGER gpkg_tile_matrix_zoom_level_update BEFORE UPDATE of zoom_level ON gpkg_tile_matrix FOR EACH ROW BEGIN SELECT RAISE(ABORT, 'update on table ''gpkg_tile_matrix'' violates constraint: zoom_level cannot be less than 0') WHERE (NEW.zoom_level < 0); END;
CREATE TRIGGER gpkg_tile_matrix_matrix_width_insert BEFORE INSERT ON gpkg_tile_matrix FOR EACH ROW BEGIN SELECT RAISE(ABORT, 'insert on table ''gpkg_tile_matrix'' violates constraint: matrix_width cannot be less than 1') WHERE (NEW.matrix_width < 1); END;
CREATE TRIGGER gpkg_tile_matrix_matrix_width_update BEFORE UPDATE OF matrix_width ON gpkg_tile_matrix FOR EACH ROW BEGIN SELECT RAISE(ABORT, 'update on table ''gpkg_tile_matrix'' violates constraint: matrix_width cannot be less than 1') WHERE (NEW.matrix_width < 1); END;
CREATE TRIGGER gpkg_tile_matrix_matrix_height_insert BEFORE INSERT ON gpkg_tile_matrix FOR EACH ROW BEGIN SELECT RAISE(ABORT, 'insert on table ''gpkg_tile_matrix'' violates constraint: matrix_height cannot be less than 1') WHERE (NEW.matrix_height < 1); END;
CREATE TRIGGER gpkg_tile_matrix_matrix_height_update BEFORE UPDATE OF matrix_height ON gpkg_tile_matrix FOR EACH ROW BEGIN SELECT RAISE(ABORT, 'update on table ''gpkg_tile_matrix'' violates constraint: matrix_height cannot be less than 1') WHERE (NEW.matrix_height < 1); END;
CREATE TRIGGER gpkg_tile_matrix_pixel_x_size_insert BEFORE INSERT ON gpkg_tile_matrix FOR EACH ROW BEGIN SELECT RAISE(ABORT, 'insert on table ''gpkg_tile_matrix'' violates constraint: pixel_x_size must be greater than 0') WHERE NOT (NEW.pixel_x_size > 0); END;
CREATE TRIGGER gpkg_tile_matrix_pixel_x_size_update BEFORE UPDATE OF pixel_x_size ON gpkg_tile_matrix FOR EACH ROW BEGIN SELECT RAISE(ABORT, 'update on table ''gpkg_tile_matrix'' violates constraint: pixel_x_size must be greater than 0') WHERE NOT (NEW.pixel_x_size > 0); END;
CREATE TRIGGER gpkg_tile_matrix_pixel_y_size_insert BEFORE INSERT ON gpkg_tile_matrix FOR EACH ROW BEGIN SELECT RAISE(ABORT, 'insert on table ''gpkg_tile_matrix'' violates constraint: pixel_y_size must be greater than 0') WHERE NOT (NEW.pixel_y_size > 0); END;
CREATE TRIGGER gpkg_tile_matrix_pixel_y_size_update BEFORE UPDATE OF pixel_y_size ON gpkg_tile_matrix FOR EACH ROW BEGIN SELECT RAISE(ABORT, 'update on table ''gpkg_tile_matrix'' violates constraint: pixel_y_size must be greater than 0') WHERE NOT (NEW.pixel_y_size > 0); END;
CREATE TRIGGER trigger_insert_feature_count_admins AFTER INSERT ON admins BEGIN UPDATE gpkg_ogr_contents SET feature_count = feature_count + 1 WHERE lower(table_name) = lower('admins'); END;
CREATE TRIGGER trigger_delete_feature_count_admins AFTER DELETE ON admins BEGIN UPDATE gpkg_ogr_contents SET feature_count = feature_count - 1 WHERE lower(table_name) = lower('admins'); END;
CREATE TRIGGER rtree_admins_shape_insert AFTER INSERT ON admins WHEN (new.shape NOT NULL AND NOT ST_IsEmpty(NEW.shape)) BEGIN INSERT OR REPLACE INTO rtree_admins_shape VALUES (NEW.id,ST_MinX(NEW.shape), ST_MaxX(NEW.shape),ST_MinY(NEW.shape), ST_MaxY(NEW.shape)); END;
CREATE TRIGGER rtree_admins_shape_update1 AFTER UPDATE OF shape ON admins WHEN OLD.id = NEW.id AND (NEW.shape NOTNULL AND NOT ST_IsEmpty(NEW.shape)) BEGIN INSERT OR REPLACE INTO rtree_admins_shape VALUES (NEW.id,ST_MinX(NEW.shape), ST_MaxX(NEW.shape),ST_MinY(NEW.shape), ST_MaxY(NEW.shape)); END;
CREATE TRIGGER rtree_admins_shape_update2 AFTER UPDATE OF shape ON admins WHEN OLD.id = NEW.id AND (NEW.shape ISNULL OR ST_IsEmpty(NEW.shape)) BEGIN DELETE FROM rtree_admins_shape WHERE id = OLD.id; END;
CREATE TRIGGER rtree_admins_shape_update3 AFTER UPDATE ON admins WHEN OLD.id != NEW.id AND (NEW.shape NOTNULL AND NOT ST_IsEmpty(NEW.shape)) BEGIN DELETE FROM rtree_admins_shape WHERE id = OLD.id; INSERT OR REPLACE INTO rtree_admins_shape VALUES (NEW.id,ST_MinX(NEW.shape), ST_MaxX(NEW.shape),ST_MinY(NEW.shape), ST_MaxY(NEW.shape)); END;
CREATE TRIGGER rtree_admins_shape_update4 AFTER UPDATE ON admins WHEN OLD.id != NEW.id AND (NEW.shape ISNULL OR ST_IsEmpty(NEW.shape)) BEGIN DELETE FROM rtree_admins_shape WHERE id IN (OLD.id, NEW.id); END;
CREATE TRIGGER rtree_admins_shape_delete AFTER DELETE ON admins WHEN old.shape NOT NULL BEGIN DELETE FROM rtree_admins_shape WHERE id = OLD.id; END;
CREATE TRIGGER trigger_insert_feature_count_names AFTER INSERT ON names BEGIN UPDATE gpkg_ogr_contents SET feature_count = feature_count + 1 WHERE lower(table_name) = lower('names'); END;
CREATE TRIGGER trigger_delete_feature_count_names AFTER DELETE ON names BEGIN UPDATE gpkg_ogr_contents SET feature_count = feature_count - 1 WHERE lower(table_name) = lower('names'); END;

COMMIT;
