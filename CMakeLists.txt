cmake_minimum_required(VERSION 3.16)
project(mixxx-mk3 C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

add_subdirectory(external/mk3)

if(EXISTS ${CMAKE_SOURCE_DIR}/external/mpi-tools/mk3_test)
    add_subdirectory(external/mpi-tools/mk3_test)
endif()
if(EXISTS ${CMAKE_SOURCE_DIR}/external/mpi-tools/mk3_cli)
    add_subdirectory(external/mpi-tools/mk3_cli)
endif()

add_subdirectory(screen-daemon)
