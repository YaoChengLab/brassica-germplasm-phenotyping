# Demo data

`crops/` holds 69 single-plant images of one plant: batch 2025B08, accession s0123, treatment Control, plant 3 (directory `rep-3`). They are 600 x 600 px crops cut from the frames of camera A2-104, which photographs the plant once an hour from 06:00 to 18:00.

| Days after sowing | Date | Images |
|---|---|---|
| 13 | 2025-07-16 | 13 |
| 18 | 2025-07-21 | 13 |
| 23 | 2025-07-26 | 13 |
| 29 | 2025-08-01 | 13 |
| 34 | 2025-08-06 | 13 |
| 39 | 2025-08-11 | 4 |

Every image of each day is included because leaf ownership is decided by a majority vote over all images of the same day. On day 39 the plant was moved out of the chamber after 09:00, so only the 06:00 to 09:00 images exist.

The file name carries the camera and the capture time: `pic<camera>-<YYYYMMDDHHMM>_<accession>_<plant>.png`.

The raw camera frames are not included. To run the demo, see `../imaging/README.md`.
