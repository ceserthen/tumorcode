cmake \
    -DCMAKE_INSTALL_PREFIX=/localdisk/tc_install \
    -DCMAKE_BUILD_TYPE=Release \
    -DPYTHON_NUMPY_INCLUDE_DIR=/usr/include/python2.7/numpy \
    -DADDITIONAL_INCLUDE_DIRS="/localdisk/gitcodes/HDF5-cpp-wrapper;/localdisk/gitcodes/numpycpp" \
    -DADDITIONAL_LIBRARY_DIRS=/localdisk/gitcodes/numpycpp/build \
    $1
