#import random
from numpy import random
import numpy as np

class IdGenerator:
    released_ids = []
    next_id = 0

    def __init__(self):
        self.released_ids = []
        self.next_id = np.int64(0)

    def nextID(self):
        n = len(self.released_ids)
        if n == 0:
            result = self.next_id
            self.next_id += 1
            return np.int64(result)
        else:
            result = self.released_ids.pop(n-1)
            return np.int64(result)

    def releaseID(self, id):
        self.released_ids.append(id)

    def preGenerateIDs(self, high_value):
        if len(self.released_ids) > 0:
            self.released_ids.clear()
        #for i in range(0, high_value):
        #    self.released_ids.append(i)
        self.released_ids = [i for i in range(0, high_value)]
        self.next_id = high_value

    def permuteIDs(self):
        n = len(self.released_ids)
        indices = random.randint(0, n, 2*n)
        for index in indices:
            id = self.released_ids.pop(index)
            self.released_ids.append(id)

        #for iter in range(0, 2*n):
        #    index = random.randint(0, n)
        #    id = self.released_ids.pop(index)
        #    self.released_ids.append(id)

    def __len__(self):
        return self.next_id

class SpecialIdGenerator:
    timebounds  = np.zeros(2, dtype=np.float64)
    depthbounds = np.zeros(2, dtype=np.float32)
    local_ids = 0

    def __init__(self):
        self.timebounds  = np.zeros(2, dtype=np.float64)
        self.depthbounds = np.zeros(2, dtype=np.float32)
        self.local_ids = np.zeros((360, 180, 128, 256), dtype=np.int32)

    def setTimeLine(self, min_time=0.0, max_time=1.0):
        self.timebounds = np.array([min_time, max_time], dtype=np.float64)

    def setDepthLimits(self, min_dept=0.0, max_depth=1.0):
        self.depthbounds = np.array([min_dept, max_depth], dtype=np.float32)

    def getID(self, lon, lat, depth, time):
        # lon_discrete = np.float32(np.int32(lon))
        lon_discrete = np.int32(lon)
        # lat_discrete = np.float32(np.int32(lat))
        lat_discrete = np.int32(lat)
        depth_discrete = (depth-self.depthbounds[0])/(self.depthbounds[1]-self.depthbounds[0])
        # depth_discrete = np.float32(np.int32(128.0*depth_discrete))
        depth_discrete = np.int32(127.0 * depth_discrete)
        time_discrete = (time-self.timebounds[0])/(self.timebounds[1]-self.timebounds[0])
        # time_discrete = np.float32(np.int32(256.0*time_discrete))
        time_discrete = np.int32(255.0 * time_discrete)
        lon_index = np.int32(lon_discrete)+180
        lat_index = np.int32(lat_discrete)+90
        depth_index = np.int32(depth_discrete)
        time_index = np.int32(time_discrete)
        local_index = self.local_ids[lon_index, lat_index, depth_index, time_index]
        self.local_ids[lon_index, lat_index, depth_index, time_index] += 1
        # id = np.bitwise_or(np.bitwise_or(np.bitwise_or(np.left_shift(lon_index, 23), np.left_shift(lat_index, 15)), np.left_shift(depth_index, 8)), time)
        id = np.left_shift(lon_index, 23) + np.left_shift(lat_index, 15) + np.left_shift(depth_index, 8) + time
        id = np.int64(id)
        id = np.bitwise_or(np.left_shift(id, 32), np.int64(local_index))
        return id

