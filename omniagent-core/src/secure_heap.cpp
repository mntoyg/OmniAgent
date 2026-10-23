#include "omniagent/secure_memory.hpp"

#include <algorithm>
#include <cerrno>
#include <cstdlib>
#include <cstring>
#include <malloc.h>
#include <new>

#ifndef __GLIBC__
#error "Secure heap requires glibc malloc_usable_size"
#endif

extern "C" void __real_free(void*) noexcept;
#ifdef OMNI_TEST_HEAP_OBSERVER
extern "C" void omni_test_before_release(const void*, std::size_t) noexcept;
#endif

namespace omniagent::detail {
void wipe_heap_allocation(void* memory) noexcept {
    if (memory != nullptr) {
        secure_zero(memory, malloc_usable_size(memory));
    }
}
} // namespace omniagent::detail

extern "C" void __wrap_free(void* memory) noexcept {
    omniagent::detail::wipe_heap_allocation(memory);
#ifdef OMNI_TEST_HEAP_OBSERVER
    if (memory != nullptr) { omni_test_before_release(memory, malloc_usable_size(memory)); }
#endif
    __real_free(memory);
}

// libc realloc may release or move a block without clearing the old copy.
extern "C" void* __wrap_realloc(void* memory, std::size_t bytes) noexcept {
    if (memory == nullptr) {
        return std::malloc(bytes);
    }
    if (bytes == 0) {
        __wrap_free(memory);
        return nullptr;
    }
    void* replacement = std::malloc(bytes);
    if (replacement == nullptr) {
        return nullptr; // Original allocation remains valid on failure.
    }
    std::memcpy(replacement, memory, std::min(bytes, malloc_usable_size(memory)));
    __wrap_free(memory);
    return replacement;
}

// Replacing all delete variants also covers containers in the C++ runtime.
void operator delete(void* memory) noexcept { __wrap_free(memory); }
void operator delete[](void* memory) noexcept { __wrap_free(memory); }
void operator delete(void* memory, std::size_t) noexcept { __wrap_free(memory); }
void operator delete[](void* memory, std::size_t) noexcept { __wrap_free(memory); }
void operator delete(void* memory, std::align_val_t) noexcept { __wrap_free(memory); }
void operator delete[](void* memory, std::align_val_t) noexcept { __wrap_free(memory); }
void operator delete(void* memory, std::size_t, std::align_val_t) noexcept { __wrap_free(memory); }
void operator delete[](void* memory, std::size_t, std::align_val_t) noexcept { __wrap_free(memory); }
void operator delete(void* memory, const std::nothrow_t&) noexcept { __wrap_free(memory); }
void operator delete[](void* memory, const std::nothrow_t&) noexcept { __wrap_free(memory); }
void operator delete(void* memory, std::align_val_t, const std::nothrow_t&) noexcept { __wrap_free(memory); }
void operator delete[](void* memory, std::align_val_t, const std::nothrow_t&) noexcept { __wrap_free(memory); }
