import _ctypes
#import ctypes
import subprocess
import numpy.ctypeslib as npct
from weakref import finalize
#from ast import FunctionDef
#from ast import parse
#from copy import deepcopy
import os
import sys
import package_globals
from struct import calcsize
from time import sleep

try:
    from mpi4py import MPI
except:
    MPI = None

class LibraryRegisterC:
    _data = {}
    def __init__(self):
        self._data = {}

    def __del__(self):
        for entry in self._data:
            while entry.register_count > 0:
                sleep(0.1)
            entry.unload_library()
            del entry

    def load(self, libname):
        if libname not in self._data.keys():
            self._data[libname] = InterfaceC("node")
        if not self._data[libname].is_compiled():
            self._data[libname].compile_library()
        if not self._data[libname].is_loaded():
            self._data[libname].load_library()

    def unload(self, libname):
        if libname in self._data.keys():
            self._data[libname].unload_library()
        #    del self._data[libname]

    def __getitem__(self, item):
        return self.get(item)

    def get(self, libname):
        #if libname not in self._data.keys():
        #    self.load(libname)
        if libname in self._data.keys():
            return self._data[libname]
        return None

    def register(self, libname):
        #if libname not in self._data.keys():
        #    self.load(libname)
        if libname in self._data.keys():
            self._data[libname].register()

    def deregister(self, libname):
        if libname in self._data.keys():
            self._data[libname].unregister()
        #    if self._data[libname].register_count <= 0:
        #        self.unload(libname)

class InterfaceC:

    def __init__(self, c_file_name):
        basename = c_file_name
        self.src_file = "%s.c" % basename
        self.lib_file = "%s.%s" % (basename, 'dll' if sys.platform == 'win32' else 'so')
        self.log_file = "%s.log" % basename

        self.compiler = GNUCompiler()
        self.compiled = False
        self.loaded = False
        self.libc = None
        self.register_count = 0

    def __del__(self):
        self.unload_library()
        self.cleanup_files()

    def is_compiled(self):
        return self.compiled

    def is_loaded(self):
        return self.loaded

    def compile_library(self):
        """ Writes kernel code to file and compiles it."""
        if not self.compiled:
            self.compiler.compile(self.src_file, self.lib_file, self.log_file)
            #logger.info("Compiled %s ==> %s" % (self.name, self.lib_file))
            #self._cleanup_files = finalize(self, package_globals.cleanup_remove_files, self.lib_file, self.log_file)
            self.compiled = True

    def cleanup_files(self):
        if os.path.isfile(self.lib_file):
            [os.remove(s) for s in [self.lib_file, self.log_file]]

    def unload_library(self):
        if self.libc is not None and self.compiled and self.loaded:
            _ctypes.FreeLibrary(self.libc._handle) if sys.platform == 'win32' else _ctypes.dlclose(self.libc._handle)
            del self.libc
            self.libc = None
            self.loaded = False

    def load_library(self):
        if self.libc is None and self.compiled and not self.loaded:
            self.libc = npct.load_library(self.lib_file, '.')
            # self._cleanup_lib = finalize(self, package_globals.cleanup_unload_lib, self.libc)
            self.loaded = True

    def register(self):
        self.register_count += 1
        # print("lib '{}' register (count: {})".format(self.lib_file, self.register_count))

    def unregister(self):
        self.register_count -= 1
        # print("lib '{}' de-register (count: {})".format(self.lib_file, self.register_count))

    def load_functions(self, function_param_array=[]):
        """

        :param function_name_array: array of dictionary {"name": str, "return": type, "arguments": [type, ...]}
        :return: dict (function_name -> function_handler)
        """
        result = dict()
        if self.libc is None or not self.compiled or not self.loaded:
            return result
        for function_param in function_param_array:
            if isinstance(function_param, dict) and \
                    isinstance(function_param["name"], str) and \
                    isinstance(function_param["return"], type) or function_param["return"] is None and \
                    isinstance(function_param["arguments"], list):
                result[function_param["name"]] = self.libc[function_param["name"]]
                result[function_param["name"]].restype = function_param["return"]
                result[function_param["name"]].argtypes = function_param["arguments"]
        return result


def wrap_function(lib, funcname, restype, argtypes):
    """Simplify wrapping ctypes functions"""
    func = lib.__getattr__(funcname)
    func.restype = restype
    func.argtypes = argtypes
    return func

class CCompiler(object):
    """A compiler object for creating and loading shared libraries.

    :arg cc: C compiler executable (uses environment variable ``CC`` if not provided).
    :arg cppargs: A list of arguments to the C compiler (optional).
    :arg ldargs: A list of arguments to the linker (optional)."""

    def __init__(self, cc=None, cppargs=None, ldargs=None):
        if cppargs is None:
            cppargs = []
        if ldargs is None:
            ldargs = []

        self._cc = os.getenv('CC') if cc is None else cc
        self._cppargs = cppargs
        self._ldargs = ldargs

    def compile(self, src, obj, log):
        cc = [self._cc] + self._cppargs + ['-o', obj, src] + self._ldargs
        with open(log, 'w') as logfile:
            logfile.write("Compiling: %s\n" % " ".join(cc))
            try:
                subprocess.check_call(cc, stdout=logfile, stderr=logfile)
            except OSError:
                err = """OSError during compilation
Please check if compiler exists: %s""" % self._cc
                raise RuntimeError(err)
            except subprocess.CalledProcessError:
                with open(log, 'r') as logfile2:
                    err = """Error during compilation:
Compilation command: %s
Source file: %s
Log file: %s

Log output: %s""" % (" ".join(cc), src, logfile.name, logfile2.read())
                raise RuntimeError(err)


class GNUCompiler(CCompiler):
    """A compiler object for the GNU Linux toolchain.

    :arg cppargs: A list of arguments to pass to the C compiler
         (optional).
    :arg ldargs: A list of arguments to pass to the linker (optional)."""
    def __init__(self, cppargs=None, ldargs=None):
        if cppargs is None:
            cppargs = []
        if ldargs is None:
            ldargs = []

        opt_flags = ['-g', '-O3']
        arch_flag = ['-m64' if calcsize("P") == 8 else '-m32']
        cppargs = ['-Wall', '-fPIC', '-I%s' % os.path.join(package_globals.get_package_dir(), 'include')] + opt_flags + cppargs
        cppargs += arch_flag
        ldargs = ['-shared'] + ldargs + arch_flag
        #compiler = "mpicc" if MPI else "gcc"
        cc_env = os.getenv('CC')
        compiler = "mpicc" if MPI else "gcc" if cc_env is None else cc_env
        super(GNUCompiler, self).__init__(compiler, cppargs=cppargs, ldargs=ldargs)








#    fargs = [byref(f.ctypes_struct) for f in self.field_args.values()]
#    fargs += [c_double(f) for f in self.const_args.values()]
#    particle_data = byref(pset.ctypes_struct)
#    return self._function(c_int(len(pset)), particle_data, c_double(endtime), c_double(dt), *fargs)







