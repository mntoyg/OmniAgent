#pragma once
#include <atomic>
#include <cstddef>

namespace omniagent {

// Volatile stores cannot be removed as dead stores, including under LTO.
inline void secure_zero(void* memory, std::size_t bytes) noexcept {
    auto* cursor = static_cast<volatile unsigned char*>(memory);
    while (bytes-- != 0) {
        *cursor++ = 0;
    }
    std::atomic_signal_fence(std::memory_order_seq_cst);
}

namespace detail {
// Internal only; used by all delete/free/realloc paths and by regression tests.
// Must receive a live glibc allocation, never a stack or mmap address.
void wipe_heap_allocation(void* memory) noexcept;
} // namespace detail
} // namespace omniagent
