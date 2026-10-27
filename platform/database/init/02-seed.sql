-- Reference data for the demo plant: batch 2025B08, accession s0123,
-- treatment Control, plant 3, photographed by camera A2-104 in chamber G120
-- after nursery in R141. Batch registration and ingest look these rows up by
-- code; the batch and its plants are created through the platform, not here.
-- IDs match the database the manuscript was produced from, so the example
-- batch metadata can name growth condition 7 directly.

BEGIN;

INSERT INTO public.growth_chambers (id, chamber_code) VALUES
    (1, 'R141'),
    (3, 'G120');

INSERT INTO public.racks (id, rack_code, chamber_id, notes) VALUES
    (2,  'A1_2', 3, NULL),
    (29, NULL,   1, 'Default rack for R141 when the shelf is not recorded');

INSERT INTO public.sensors (id, sensor_code, sensor_type, rack_id, chamber_id, notes, modality, cadence, view_angle) VALUES
    (13, NULL,     'arduino', 29, 1, 'Default sensor for R141 when the shelf is not recorded', 'env_arduino', 'timeseries', NULL),
    (32, 'A2-104', 'raspi',   2,  3, 'RasPi A2-104', 'rgb_raspi', 'timeseries', 'topview');

INSERT INTO public.growth_conditions (id) VALUES (7);

INSERT INTO public.treatments (id, treatment_code) VALUES (1, 'Control');

-- Only the fields published in Supplementary Table S2: accession, basic
-- morphotype and recorded genome type.
INSERT INTO public.cultivars (id, cultivar_code, common_name, genome_type) VALUES
    (123, 's0123', 'Pak choi', 'AA');

SELECT setval(pg_get_serial_sequence('public.growth_chambers', 'id'), (SELECT max(id) FROM public.growth_chambers));
SELECT setval(pg_get_serial_sequence('public.racks', 'id'), (SELECT max(id) FROM public.racks));
SELECT setval(pg_get_serial_sequence('public.sensors', 'id'), (SELECT max(id) FROM public.sensors));
SELECT setval(pg_get_serial_sequence('public.growth_conditions', 'id'), (SELECT max(id) FROM public.growth_conditions));
SELECT setval(pg_get_serial_sequence('public.treatments', 'id'), (SELECT max(id) FROM public.treatments));
SELECT setval(pg_get_serial_sequence('public.cultivars', 'id'), (SELECT max(id) FROM public.cultivars));

COMMIT;
