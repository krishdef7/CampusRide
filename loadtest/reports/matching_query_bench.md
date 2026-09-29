# Matching query benchmark (simulated drivers)

Single connection, 300 claims per cell, each in a rolled-back transaction. Radius 1500 m. 50% of drivers available. Latency = one DB round trip (p50 / p95 ms).

| Scenario | Drivers | Avail. in radius | knn_partial_gist | radius_sort_gist | knn_no_index | app_side_scan |
|---|---|---|---|---|---|---|
| campus | 1,000 | 394 | 0.87 / 1.04 | 2.09 / 2.50 | 2.38 / 2.81 | 2.54 / 2.86 |
| campus | 10,000 | 3,992 | 0.92 / 1.19 | 15.39 / 17.49 | 34.39 / 37.98 | 9.24 / 19.66 |
| campus | 100,000 | 39,178 | 0.98 / 1.19 | 144.81 / 165.34 | 410.69 / 453.14 | 89.50 / 103.30 |
| city | 1,000 | 8 | 1.21 / 1.44 | 0.77 / 0.93 | 2.22 / 2.63 | 2.50 / 2.79 |
| city | 10,000 | 98 | 1.78 / 2.13 | 1.17 / 1.38 | 36.15 / 40.54 | 9.08 / 18.69 |
| city | 100,000 | 1,072 | 1.04 / 1.22 | 6.13 / 6.80 | 422.51 / 458.08 | 90.70 / 100.25 |

Production query plan (city, largest fleet):

```
CTE Scan on assigned a (actual time=3.678..3.684 rows=1 loops=1)
  Buffers: shared hit=1049
  CTE ride
    ->  LockRows (actual time=0.012..0.014 rows=1 loops=1)
          Buffers: shared hit=5
          ->  Index Scan using rides_pkey on rides (actual time=0.003..0.005 rows=1 loops=1)
                Index Cond: (id = '1'::bigint)
                Filter: (status = ANY ('{searching,scheduled}'::text[]))
                Buffers: shared hit=3
  CTE best
    ->  Limit (actual time=3.531..3.533 rows=1 loops=1)
          Buffers: shared hit=1023
          ->  LockRows (actual time=3.531..3.533 rows=1 loops=1)
                Buffers: shared hit=1023
                ->  Result (actual time=3.528..3.530 rows=1 loops=1)
                      Buffers: shared hit=1022
                      ->  Sort (actual time=3.525..3.527 rows=1 loops=1)
                            Sort Key: ((st_distance(d.location, '0101000020E61000006FF085C954795340228E75711BDD3D40'::geography, true) + (('150'::smallint * (d.capacity - '1'::smallint)))::double precision))
                            Sort Method: quicksort  Memory: 27kB
                            Buffers: shared hit=1022
                            ->  Nested Loop (actual time=3.432..3.517 rows=16 loops=1)
                                  Buffers: shared hit=1022
                                  ->  CTE Scan on ride (actual time=0.016..0.018 rows=1 loops=1)
                                        Buffers: shared hit=5
                                  ->  Nested Loop (actual time=3.409..3.469 rows=16 loops=1)
                                        Buffers: shared hit=1017
                                        ->  Subquery Scan on knn (actual time=3.371..3.378 rows=16 loops=1)
                                              Buffers: shared hit=969
                                              ->  Limit (actual time=3.368..3.371 rows=16 loops=1)
                                                    Buffers: shared hit=969
                                                    ->  Sort (actual time=3.368..3.369 rows=16 loops=1)
                                                          Sort Key: ((drivers.location <-> '0101000020E61000006FF085C954795340228E75711BDD3D40'::geography))
                                                          Sort Method: top-N heapsort  Memory: 26kB
                                                          Buffers: shared hit=969
                                                          ->  Bitmap Heap Scan on drivers (actual time=0.447..3.252 rows=1068 loops=1)
                                                                Recheck Cond: (status = 'available'::text)
                                                                Filter: ((capacity >= '1'::smallint) AND (last_seen > (now() - '2777:46:40'::interval)) AND st_dwithin(location, '0101000020E61000006FF085C954795340228E75711BDD3D40'::geography, '1500'::double precision, true))
                                                                Rows Removed by Filter: 567
                                                                Heap Blocks: exact=937
                                                                Buffers: shared hit=969
                                                                ->  Bitmap Index Scan on drivers_available_location_gix (actual time=0.345..0.345 rows=1635 loops=1)
                                                                      Index Cond: (location && _st_expand('0101000020E61000006FF085C954795340228E75711BDD3D40'::geography, '1500'::double precision))
                                                                      Buffers: shared hit=32
                                        ->  Index Scan using drivers_pkey on drivers d (actual time=0.005..0.005 rows=1 loops=16)
                                              Index Cond: (id = knn.id)
                                              Filter: (status = 'available'::text)
                                              Buffers: shared hit=48
  CTE claimed
    ->  Update on drivers d_1 (actual time=3.611..3.612 rows=1 loops=1)
          Buffers: shared hit=1034
          ->  Nested Loop (actual time=3.550..3.551 rows=1 loops=1)
                Buffers: shared hit=1026
                ->  CTE Scan on best (actual time=3.534..3.534 rows=1 loops=1)
                      Buffers: shared hit=1023
                ->  Index Scan using drivers_pkey on drivers d_1 (actual time=0.015..0.015 rows=1 loops=1)
                      Index Cond: (id = best.id)
                      Filter: (status = 'available'::text)
                      Buffers: shared hit=3
  CTE assigned
    ->  Update on rides r (actual time=3.676..3.678 rows=1 loops=1)
          Buffers: shared hit=1049
          ->  Nested Loop (actual time=3.626..3.628 rows=1 loops=1)
                Buffers: shared hit=1037
                ->  Index Scan using rides_pkey on rides r (actual time=0.010..0.011 rows=1 loops=1)
                      Index Cond: (id = '1'::bigint)
                      Buffers: shared hit=3
                ->  CTE Scan on claimed (actual time=3.614..3.615 rows=1 loops=1)
                      Buffers: shared hit=1034
Planning:
  Buffers: shared hit=25
Planning Time: 1.449 ms
Trigger for constraint rides_driver_id_fkey on rides: time=0.027 calls=1
Execution Time: 3.882 ms
```
