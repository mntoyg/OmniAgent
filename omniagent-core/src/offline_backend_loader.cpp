#include "ggml-backend-dl.h"

// Keep the backend registry ABI but permanently refuse dynamic code loading.
dl_handle* dl_load_library(const fs::path&) { return nullptr; }
void* dl_get_sym(dl_handle*, const char*) { return nullptr; }
const char* dl_error() { return "dynamic backends disabled by offline runtime"; }
