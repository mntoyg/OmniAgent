#include <cstdio>
#include <cstdlib>

// A harmless local library that makes any accidental dlopen observable.
__attribute__((constructor)) static void probe_loaded() {
    const char* path = std::getenv("OMNI_PROBE_FILE");
    if (path != nullptr) {
        if (FILE* file = std::fopen(path, "wb")) { std::fclose(file); }
    }
}
