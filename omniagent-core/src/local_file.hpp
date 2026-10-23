#pragma once
#include "omniagent/local_inference_engine.hpp"

namespace omniagent::detail {
struct OpenedFile {
    Error error;
    int fd;
};
OpenedFile open_local_file(std::string_view path, bool audit, std::uint64_t max_bytes) noexcept;
bool valid_config(const Config& config) noexcept;
} // namespace omniagent::detail
