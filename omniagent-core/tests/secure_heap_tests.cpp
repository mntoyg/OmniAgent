#include "omniagent/secure_memory.hpp"
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <malloc.h>
#include <limits>
#include <new>

extern "C" void* __wrap_realloc(void*, std::size_t) noexcept;

namespace {
bool observe = false;
std::size_t releases = 0;
std::size_t failures = 0;
void fill_allocation(void* memory, unsigned char value) {
    auto* bytes = static_cast<volatile unsigned char*>(memory);
    for (std::size_t i = 0, size = malloc_usable_size(memory); i < size; ++i) { bytes[i] = value; }
}
}

extern "C" void omni_test_before_release(const void* memory, std::size_t size) noexcept {
    if (!observe) { return; }
    ++releases;
    const auto* bytes = static_cast<const unsigned char*>(memory);
    for (std::size_t i = 0; i < size; ++i) {
        if (bytes[i] != 0) { ++failures; break; }
    }
}

int main() {
    observe = true;
    auto* bytes = static_cast<unsigned char*>(std::malloc(33));
    if (bytes == nullptr) { return 1; }
    const auto capacity = malloc_usable_size(bytes);
    fill_allocation(bytes, 0xA5); // Includes allocator padding.
    omniagent::detail::wipe_heap_allocation(bytes);
    for (std::size_t i = 0; i < capacity; ++i) {
        if (bytes[i] != 0) { return 2; }
    }
    fill_allocation(bytes, 0xA5);
    auto* grown = static_cast<unsigned char*>(std::realloc(bytes, 100));
    if (grown == nullptr || !std::all_of(grown, grown + 33, [](auto b) { return b == 0xA5; })) { return 3; }
    fill_allocation(grown, 0xFE);
    std::free(grown);

    auto* value = ::operator new[](73);
    fill_allocation(value, 0xBB);
    ::operator delete[](value);
    auto* aligned = ::operator new(128, std::align_val_t(64));
    fill_allocation(aligned, 0xCC);
    ::operator delete(aligned, std::align_val_t(64));
    auto* zero_size = std::malloc(31);
    fill_allocation(zero_size, 0xDD);
    if (std::realloc(zero_size, 0) != nullptr) { return 4; }
    std::free(nullptr);
    auto* preserved = static_cast<unsigned char*>(std::malloc(19));
    if (preserved == nullptr) { return 6; }
    fill_allocation(preserved, 0xB1);
    volatile std::size_t impossible_size = std::numeric_limits<std::size_t>::max();
    if (__wrap_realloc(preserved, impossible_size) != nullptr || preserved[0] != 0xB1) { return 7; }
    std::free(preserved);
    observe = false;
    if (failures != 0 || releases < 5) { return 5; }
    std::puts("Secure heap: every observed release was zero, including realloc and padding");
    return 0;
}
