from ctypes import c_void_p
from operator import attrgetter

import numpy as np

#from parcels.field import Field
from parcels_mocks import Field
#from parcels.tools.error import ErrorCode
from parcels_mocks import StatusCode as ErrorCode


__all__ = ['ScipyParticle', 'JITParticle', 'Variable']

indicators_64bit = [np.float64, np.int64, c_void_p]

class Variable(object):
    """Descriptor class that delegates data access to particle data

    :param name: Variable name as used within kernels
    :param dtype: Data type (numpy.dtype) of the variable
    :param initial: Initial value of the variable. Note that this can also be a Field object,
             which will then be sampled at the location of the particle
    :param to_write: Boolean to control whether Variable is written to NetCDF file
    """
    def __init__(self, name, dtype=np.float32, initial=0, to_write=True):
        if name == 'z':
            raise NotImplementedError("Custom Variable name 'z' is not allowed, as it is used for depth in ParticleFile")
        self.name = name
        self.dtype = dtype
        self.initial = initial
        self.to_write = to_write

    def __get__(self, instance, cls):
        if instance is None:
            return self
        if issubclass(cls, JITParticle):
            return instance._cptr.__getitem__(self.name)
        else:
            return getattr(instance, "_%s" % self.name, self.initial)

    def __set__(self, instance, value):
        if isinstance(instance, JITParticle):
            instance._cptr.__setitem__(self.name, value)
        else:
            setattr(instance, "_%s" % self.name, value)

    def random(self, pinstance):
        if isinstance(pinstance, JITParticle):
            pinstance._cptr.__setitem__(self.name, np.random.rand(1).astype(dtype=self.dtype))
        else:
            setattr(pinstance, "_%s" % self.name, np.random.rand(1).astype(dtype=self.dtype))

    def __repr__(self):
        return "PVar<%s|%s>" % (self.name, self.dtype)

    def is64bit(self):
        """Check whether variable is 64-bit"""
        #return True if self.dtype == np.float64 or self.dtype == np.int64 or self.dtype == c_void_p else False
        #return True if self.dtype in [np.float64, np.int64, c_void_p] else False
        return True if self.dtype in indicators_64bit else False


class ParticleType(object):
    """Class encapsulating the type information for custom particles

    :param user_vars: Optional list of (name, dtype) tuples for custom variables
    """

    def __init__(self, pclass):
        if not isinstance(pclass, type):
            raise TypeError("Class object required to derive ParticleType")
        if not issubclass(pclass, ScipyParticle):
            raise TypeError("Class object does not inherit from parcels.ScipyParticle")

        self.name = pclass.__name__
        self.uses_jit = issubclass(pclass, JITParticle)
        # Pick Variable objects out of __dict__.
        self.variables = [v for v in pclass.__dict__.values() if isinstance(v, Variable)]
        for cls in pclass.__bases__:
            if issubclass(cls, ScipyParticle):
                # Add inherited particle variables
                ptype = cls.getPType()
                self.variables = ptype.variables + self.variables
        # Sort variables with all the 64-bit first so that they are aligned for the JIT cptr
        self.variables = [v for v in self.variables if v.is64bit()] + \
                         [v for v in self.variables if not v.is64bit()]

    def __repr__(self):
        return "PType<%s>::%s" % (self.name, self.variables)

    @property
    def _cache_key(self):
        return "-".join(["%s:%s" % (v.name, v.dtype) for v in self.variables])

    @property
    def dtype(self):
        """Numpy.dtype object that defines the C struct"""
        type_list = [(v.name, v.dtype) for v in self.variables]
        for v in self.variables:
            if v.dtype not in self.supported_dtypes:
                raise RuntimeError(str(v.dtype) + " variables are not implemented in JIT mode")
        if self.size % 8 > 0:
            # Add padding to be 64-bit aligned
            type_list += [('pad', np.float32)]
        return np.dtype(type_list)

    @property
    def size(self):
        """Size of the underlying particle struct in bytes"""
        return sum([8 if v.is64bit() else 4 for v in self.variables])

    @property
    def supported_dtypes(self):
        """List of all supported numpy dtypes. All others are not supported"""

        # Developer note: other dtypes (mostly 2-byte ones) are not supported now
        # because implementing and aligning them in cgen.GenerableStruct is a
        # major headache. Perhaps in a later stage
        return [np.int32, np.int64, np.float32, np.double, np.float64, c_void_p]


class _Particle(object):
    """Private base class for all particle types"""
    lastID = 0  # class-level variable keeping track of last Particle ID used

    def __init__(self):
        ptype = self.getPType()
        # Explicit initialisation of all particle variables
        for v in ptype.variables:
            if isinstance(v.initial, attrgetter):
                initial = v.initial(self)
            elif isinstance(v.initial, Field):
                lon = self.getInitialValue(ptype, name='lon')
                lat = self.getInitialValue(ptype, name='lat')
                depth = self.getInitialValue(ptype, name='depth')
                time = self.getInitialValue(ptype, name='time')
                if time is None:
                    raise RuntimeError('Cannot initialise a Variable with a Field if no time provided. '
                                       'Add a "time=" to ParticleSet construction')
                v.initial.fieldset.computeTimeChunk(time, 0)
                initial = v.initial[time, depth, lat, lon]
            else:
                initial = v.initial
            # Enforce type of initial value
            if v.dtype != c_void_p:
                setattr(self, v.name, v.dtype(initial))

        # Placeholder for explicit error handling
        self.exception = None

    @classmethod
    def getPType(cls):
        return ParticleType(cls)

    @classmethod
    def getInitialValue(cls, ptype, name):
        return next((v.initial for v in ptype.variables if v.name is name), None)

    @classmethod
    def setLastID(cls, offset):
        _Particle.lastID = offset


class ScipyParticle(_Particle):
    """Class encapsulating the basic attributes of a particle,
    to be executed in SciPy mode

    :param lon: Initial longitude of particle
    :param lat: Initial latitude of particle
    :param depth: Initial depth of particle
    :param fieldset: :mod:`parcels.fieldset.FieldSet` object to track this particle on
    :param time: Current time of the particle

    Additional Variables can be added via the :Class Variable: objects
    """

    lon = Variable('lon', dtype=np.float32)
    lat = Variable('lat', dtype=np.float32)
    depth = Variable('depth', dtype=np.float32)
    time = Variable('time', dtype=np.float64)
    id = Variable('id', dtype=np.int32)
    dt = Variable('dt', dtype=np.float32, to_write=False)
    state = Variable('state', dtype=np.int32, initial=ErrorCode.Success, to_write=False)

    def __init__(self, lon, lat, pid, fieldset, depth=0., time=0., cptr=None):

        # Enforce default values through Variable descriptor
        type(self).lon.initial = lon
        type(self).lat.initial = lat
        type(self).depth.initial = depth
        type(self).time.initial = time
        type(self).id.initial = pid
        _Particle.lastID = max(_Particle.lastID, pid)
        type(self).dt.initial = None
        super(ScipyParticle, self).__init__()
        self._next_dt = None

    def __repr__(self):
        time_string = "not_yet_set" if (self.time is None) or (np.isnan(self.time)) else "{}".format(self.time) ## :f
        str = "P[%d](lon=%f, lat=%f, depth=%f, " % (self.id, self.lon, self.lat, self.depth)
        for var in vars(type(self)):
            if type(getattr(type(self), var)) is Variable and getattr(type(self), var).to_write is True:
                str += "%s=%f, " % (var, getattr(self, var))
        return str + "time=%s)" % time_string

    def random(self):
        ptype = self.getPType()
        # variables = {}
        for var in ptype.variables:
            var_value = getattr(self, var.name)
            var_value.random()
            setattr(self, var.name, var_value)

    def delete(self):
        self.state = ErrorCode.Delete

    def reset_state(self):
        self.state = ErrorCode.Success

    @classmethod
    def set_lonlatdepth_dtype(cls, dtype):
        cls.lon.dtype = dtype
        cls.lat.dtype = dtype
        cls.depth.dtype = dtype

    def update_next_dt(self, next_dt=None):
        if next_dt is None:
            if self._next_dt is not None:
                self.dt = self._next_dt
                self._next_dt = None
        else:
            self._next_dt = next_dt

class JITParticle(ScipyParticle):
    """Particle class for JIT-based (Just-In-Time) Particle objects

    :param lon: Initial longitude of particle
    :param lat: Initial latitude of particle
    :param fieldset: :mod:`parcels.fieldset.FieldSet` object to track this particle on
    :param dt: Execution timestep for this particle
    :param time: Current time of the particle

    Additional Variables can be added via the :Class Variable: objects

    Users should use JITParticles for faster advection computation.

    """

    cxi = Variable('cxi', dtype=np.dtype(c_void_p), to_write=False)
    cyi = Variable('cyi', dtype=np.dtype(c_void_p), to_write=False)
    czi = Variable('czi', dtype=np.dtype(c_void_p), to_write=False)
    cti = Variable('cti', dtype=np.dtype(c_void_p), to_write=False)

    def __init__(self, *args, **kwargs):
        self._cptr = kwargs.pop('cptr', None)
        if self._cptr is None:
            # Allocate data for a single particle
            ptype = self.getPType()
            # here, np.empty is potentially hazardous - the pointer should always be initialized to 0 (unless data is set)
            # self._cptr = np.empty(1, dtype=ptype.dtype)[0]
            self._cptr = np.zeros(1, dtype=ptype.dtype) # [0]
        super(JITParticle, self).__init__(*args, **kwargs)

        fieldset = kwargs.get('fieldset')
        for index in ['xi', 'yi', 'zi', 'ti']:
            if index != 'ti':
                setattr(self, index, np.zeros((fieldset.gridset.size), dtype=np.int32))
            else:
                setattr(self, index, -1*np.ones((fieldset.gridset.size), dtype=np.int32))
            setattr(self, index+'p', getattr(self, index).ctypes.data_as(c_void_p))
            setattr(self, 'c'+index, getattr(self, index+'p').value)

    def cdata(self):
        if self._cptr is None:
            return None
        return self._cptr.ctypes.data_as(c_void_p)

    def set_cptr(self, value):
        if isinstance(value, np.ndarray):
            self._cptr = value
        else:
            self._cptr = None

    def get_cptr(self):
        return self._cptr

    def reset_cptr(self):
        self._cptr=None



# ============================ #
# ======== DO NOT USE ======== #
# ============================ #
class ParticleBuffer(object):

    def __init__(self, pclass=JITParticle, lonlatdepth_dtype=None):
        if lonlatdepth_dtype is not None:
            self.lonlatdepth_dtype = lonlatdepth_dtype
        else:
            self.lonlatdepth_dtype = np.float32
        JITParticle.set_lonlatdepth_dtype(self.lonlatdepth_dtype)

        self.particles = np.empty([], dtype=pclass)
        self.pclass = pclass
        self.ptype = self.pclass.getPType()
        if self.ptype.uses_jit:
            # Allocate underlying data for C-allocated particles
            self._particle_data = np.empty([], dtype=self.ptype.dtype)

            def cptr(i):
                return self._particle_data[i]
        else:
            def cptr(i):
                return None

        self.invalid_indices = []

    def add(self, pdata):
        assert (isinstance(pdata, self.pclass))
        self.particles = np.concatenate((self.particles, pdata), 0)
        new_p_index = self.particles.shape[0]-1
        if self.ptype.uses_jit:
            self._particle_data = np.concatenate((self._particle_data, pdata.get_cptr()),0)
            new_pcdata_index = self._particle_data.shape[0]-1
            self.particles[new_p_index].set_cptr( self._particle_data[new_pcdata_index] )
        return self.particles[new_p_index]

    def invalidate(self, pdata_or_index ):
        if isinstance(pdata_or_index, self.pclass):
            index = np.where(self.particles == pdata_or_index)[0][0]
            # self.particles[index] = None
            self.invalid_indices.append(index)
        elif isinstance(pdata_or_index, int):
            if pdata_or_index >= 0 and pdata_or_index < self.particles.shape[0]:
                self.invalid_indices.append(pdata_or_index)

    def compact(self):
        removals = np.array(self.invalid_indices, dtype=np.int32)
        self.particles = np.delete(self.particles, removals)
        if self.ptype.uses_jit:
            self._particle_data = np.delete(self._particle_data, removals)
        self.invalid_indices.clear()

    def autocompact(self, condition):
        pass

    def get(self, index):
        if index >= 0 and index < self.particles.shape[0]:
            return self.particles[index]
        return None

    def __getitem__(self, item):
        return self.get(item)
