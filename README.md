# List and Set Experiments
An attempt to recreate the dynamism performance of C-like sets and lists (see Sedgwick book on Algorithms and Data Structures) in Python, to circumvent the performance malus of NumPy-like dense matrices and (fixed) arrays.

I try to use as much established libraries in Python (see 'bisect', 'sortedcollections' and 'sortedcontainers'), while preserving links to C-interaction (preferably just-in-time via CTypes).

first results:

```
Real list created.
Time adding 131072 particles (RealList): 13.388341611000001
Time delete and insert 131072 particles (RealList): 4.802947877000001
Deleting 131072 elements ...
===========================================================================
Ordered list created.
Time adding 131072 particles (OrderedList): 13.890868412
Time delete and insert 131072 particles (OrderedList): 5.314203552999999
Deleting 131072 elements ...
===========================================================================
Time adding 131072 particles (NumPy Array): 12.663392634999994
Time delete and insert 131072 particles (NumPy Array): 52.743404987999995
```

As we can see, add-and-remove actions arbitrarily in the list are done very fast (as natural to linked lists and sets),
while the fixed arrays and dense matrices in NumPy need to re-create and re-allocate memory all the time, hence the performance malus.
