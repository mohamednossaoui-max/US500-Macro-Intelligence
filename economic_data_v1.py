Run python "./economic_data_v1.py"
Traceback (most recent call last):
========================================================================
  File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/pandas/core/indexes/base.py", line 3641, in get_loc
    return self._engine.get_loc(casted_key)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "pandas/_libs/index.pyx", line 168, in pandas._libs.index.IndexEngine.get_loc
  File "pandas/_libs/index.pyx", line 197, in pandas._libs.index.IndexEngine.get_loc
  File "pandas/_libs/hashtable_class_helper.pxi", line 7668, in pandas._libs.hashtable.PyObjectHashTable.get_item
  File "pandas/_libs/hashtable_class_helper.pxi", line 7676, in pandas._libs.hashtable.PyObjectHashTable.get_item
KeyError: 'point_in_time_safe'

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "/home/runner/work/US500-Macro-Intelligence/US500-Macro-Intelligence/./economic_data_v1.py", line 419, in <module>
    main()
  File "/home/runner/work/US500-Macro-Intelligence/US500-Macro-Intelligence/./economic_data_v1.py", line 383, in main
    quality = build_quality_report(events)
US500 MACRO INTELLIGENCE
ECONOMIC INTELLIGENCE — PHASE 1A
POINT-IN-TIME DATASET + QUALITY GATE
========================================================================
              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/runner/work/US500-Macro-Intelligence/US500-Macro-Intelligence/./economic_data_v1.py", line 304, in build_quality_report
    pit_safe = int(subset["point_in_time_safe"].fillna(False).sum())
                   ~~~~~~^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/pandas/core/frame.py", line 4378, in __getitem__
    indexer = self.columns.get_loc(key)
              ^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/pandas/core/indexes/base.py", line 3648, in get_loc
    raise KeyError(key) from err
KeyError: 'point_in_time_safe'
Error: Process completed with exit code 1.
