cmake_minimum_required(VERSION 3.22)
project(omniagent_core VERSION 0.1.0 LANGUAGES C CXX)

# This runtime requires glibc's allocation-size API and GNU linker wrapping.
if(NOT CMAKE_SYSTEM_NAME STREQUAL "Linux" OR NOT CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    message(FATAL_ERROR "omniagent-core requires Linux/glibc and GCC or Clang")
endif()
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(LLAMA_SOURCE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../models/llama.cpp" CACHE PATH "Existing local llama.cpp checkout")
if(NOT EXISTS "${LLAMA_SOURCE_DIR}/include/llama.h")
    message(FATAL_ERROR "Provide a local llama.cpp checkout with -DLLAMA_SOURCE_DIR=...; this build never downloads it")
endif()
file(SHA256 "${LLAMA_SOURCE_DIR}/include/llama.h" LLAMA_API_HASH)
if(NOT LLAMA_API_HASH STREQUAL "d5cf9203bea63b575e76cba4881f29cfd1b611451578b01582b75b72ecbb04bc")
    message(FATAL_ERROR "Unsupported llama.cpp header: computed ${LLAMA_API_HASH}; expected canonical LF. CRLF may result from core.autocrlf=true or reading a Windows checkout through /mnt.")
endif()

# No common library, tools, server, app, RPC, dynamic plugins or downloads.
set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
foreach(flag IN ITEMS LLAMA_BUILD_COMMON LLAMA_BUILD_TESTS LLAMA_BUILD_TOOLS
        LLAMA_BUILD_EXAMPLES LLAMA_BUILD_SERVER LLAMA_BUILD_APP LLAMA_BUILD_UI
        LLAMA_BUILD_MTMD LLAMA_OPENSSL GGML_BACKEND_DL GGML_CPU_ALL_VARIANTS
        GGML_RPC GGML_VIRTGPU GGML_VIRTGPU_BACKEND GGML_CUDA GGML_HIP GGML_MUSA
        GGML_VULKAN GGML_METAL GGML_SYCL GGML_OPENCL GGML_OPENVINO GGML_WEBGPU
        GGML_ZDNN GGML_ET GGML_ET_SYSEMU GGML_HEXAGON GGML_ZENDNN
        GGML_BLAS GGML_ACCELERATE GGML_CPU_HBM GGML_CPU_KLEIDIAI
        GGML_OPENMP GGML_OPENMP_FETCH GGML_BUILD_TESTS GGML_BUILD_EXAMPLES)
    set(${flag} OFF CACHE BOOL "" FORCE)
endforeach()
set(GGML_CPU ON CACHE BOOL "" FORCE)
set(GGML_NATIVE OFF CACHE BOOL "" FORCE)
set(GGML_CCACHE OFF CACHE BOOL "" FORCE)
add_subdirectory("${LLAMA_SOURCE_DIR}" "llama" EXCLUDE_FROM_ALL)
# GGML_BACKEND_DL=OFF alone does not remove the explicit plugin loader.
# Replace its translation unit in this build, without editing the checkout.
get_target_property(GGML_SOURCES ggml SOURCES)
list(FILTER GGML_SOURCES EXCLUDE REGEX "(^|/)ggml-backend-dl\\.cpp$")
set_property(TARGET ggml PROPERTY SOURCES "${GGML_SOURCES}")
target_sources(ggml PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/src/offline_backend_loader.cpp")
target_include_directories(ggml PRIVATE "${LLAMA_SOURCE_DIR}/ggml/src")
find_package(Threads REQUIRED)

# Allocation interposition is mandatory, including for static libstdc++.
# It wipes backend scratch, KV, vectors, strings, padding and weights on release.
add_library(omniagent_secure_heap OBJECT src/secure_heap.cpp)
add_library(omniagent_core STATIC src/local_inference_engine.cpp src/local_file.cpp)
target_include_directories(omniagent_core PUBLIC include PRIVATE src)
target_include_directories(omniagent_secure_heap PRIVATE include)
target_compile_options(omniagent_core PRIVATE -Wall -Wextra -Wpedantic -Werror)
target_compile_options(omniagent_secure_heap PRIVATE -Wall -Wextra -Wpedantic -Werror)
target_link_libraries(omniagent_core PRIVATE llama PUBLIC Threads::Threads)
target_sources(omniagent_core INTERFACE $<TARGET_OBJECTS:omniagent_secure_heap>)
target_link_options(omniagent_core INTERFACE
    -static-libstdc++ -static-libgcc -Wl,--wrap=free -Wl,--wrap=realloc)

option(OMNI_BUILD_TESTS "Build local tests (no downloaded fixtures)" ON)
if(OMNI_BUILD_TESTS)
    enable_testing()
    find_package(Python3 REQUIRED COMPONENTS Interpreter)
    add_executable(omniagent_core_tests tests/core_tests.cpp)
    add_library(offline_plugin_probe SHARED tests/plugin_probe.cpp)
    add_dependencies(omniagent_core_tests offline_plugin_probe)
    target_compile_definitions(omniagent_core PUBLIC OMNI_CORE_TESTING=1)
    target_include_directories(omniagent_core_tests PRIVATE src)
    target_link_libraries(omniagent_core_tests PRIVATE omniagent_core llama)
    target_compile_options(omniagent_core_tests PRIVATE -Wall -Wextra -Wpedantic -Werror)
    add_test(NAME make_tiny_gguf COMMAND "${Python3_EXECUTABLE}"
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/make_tiny_gguf.py" "${CMAKE_CURRENT_BINARY_DIR}/tiny.gguf")
    set_tests_properties(make_tiny_gguf PROPERTIES FIXTURES_SETUP gguf)
    add_test(NAME core COMMAND omniagent_core_tests "${CMAKE_CURRENT_BINARY_DIR}/tiny.gguf"
        $<TARGET_FILE:offline_plugin_probe>)
    set_tests_properties(core PROPERTIES FIXTURES_REQUIRED gguf TIMEOUT 60)
    add_executable(secure_heap_tests tests/secure_heap_tests.cpp src/secure_heap.cpp)
    target_include_directories(secure_heap_tests PRIVATE include)
    target_compile_definitions(secure_heap_tests PRIVATE OMNI_TEST_HEAP_OBSERVER=1)
    target_compile_options(secure_heap_tests PRIVATE -Wall -Wextra -Wpedantic -Werror)
    target_link_options(secure_heap_tests PRIVATE
        -static-libstdc++ -static-libgcc -Wl,--wrap=free -Wl,--wrap=realloc)
    add_test(NAME secure_heap COMMAND secure_heap_tests)
    add_test(NAME offline_imports COMMAND "${CMAKE_COMMAND}" "-DNM=${CMAKE_NM}"
        "-DBINARY=$<TARGET_FILE:omniagent_core_tests>"
        -P "${CMAKE_CURRENT_SOURCE_DIR}/tests/check_imports.cmake")
endif()
