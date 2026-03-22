cmake_minimum_required(VERSION 3.16)
project(icu_core_engine CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Compiler flags
add_compile_options(
    -O2
    -Wall
    -Wextra
    -Wpedantic
    -pthread
)

# nlohmann/json (header-only, included via FetchContent)
include(FetchContent)
FetchContent_Declare(
    nlohmann_json
    URL https://github.com/nlohmann/json/releases/download/v3.11.3/json.tar.xz
    URL_HASH SHA256=d6c65aca6b1ed68e7a182f4757257b107ae403032760ed6ef121c9d55e81757d
)
FetchContent_MakeAvailable(nlohmann_json)

# Source files
set(SOURCES
    src/main.cpp
    src/vitals_simulator.cpp
    src/scheduler.cpp
    src/kafka_publisher.cpp
)

# Main executable
add_executable(icu_core_engine ${SOURCES})

target_include_directories(icu_core_engine PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_link_libraries(icu_core_engine PRIVATE
    nlohmann_json::nlohmann_json
    pthread
)

# Optional: link librdkafka when available
find_library(RDKAFKA_LIB rdkafka++ HINTS /usr/lib /usr/local/lib)
if(RDKAFKA_LIB)
    target_link_libraries(icu_core_engine PRIVATE ${RDKAFKA_LIB})
    target_compile_definitions(icu_core_engine PRIVATE USE_RDKAFKA=1)
    message(STATUS "Found librdkafka: ${RDKAFKA_LIB}")
else()
    message(WARNING "librdkafka not found – using stdout mock publisher")
endif()

# Install
install(TARGETS icu_core_engine DESTINATION bin)
