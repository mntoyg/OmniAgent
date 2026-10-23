#pragma once

#include <atomic>
#include <cstddef>
#include <cstdint>
#include <mutex>
#include <span>
#include <string_view>

struct llama_model;
struct llama_context;

namespace omniagent {

enum class Error : std::uint8_t {
    none, invalid_config, invalid_path, io, model_too_large, invalid_model,
    not_loaded, context_limit, output_limit, allocation, backend, cancelled, log_io
};

// All diagnostics are bounded static strings, never backend exception text.
std::string_view error_message(Error error) noexcept;

struct Config {
    std::uint32_t context_tokens = 2048;
    std::uint32_t batch_tokens = 128;
    std::uint32_t threads = 4;
    std::size_t max_prompt_bytes = 1024 * 1024;
    std::size_t max_output_bytes = 1024 * 1024;
    std::uint64_t max_model_bytes = 16ULL * 1024 * 1024 * 1024;
};

enum class Stop : std::uint8_t { none, end_of_generation, token_limit };
struct Generation {
    Error error = Error::none;
    Stop stop = Stop::none;
    std::size_t bytes = 0;
    std::uint32_t tokens = 0;
};

// One context per engine. Operations serialize; cancel() is lock-free.
// Linux/glibc only. Link using the CMake target to retain mandatory heap wiping.
class LocalInferenceEngine final {
public:
    explicit LocalInferenceEngine(Config config = {}) noexcept;
    ~LocalInferenceEngine() noexcept;
    LocalInferenceEngine(const LocalInferenceEngine&) = delete;
    LocalInferenceEngine& operator=(const LocalInferenceEngine&) = delete;
    LocalInferenceEngine(LocalInferenceEngine&&) = delete;
    LocalInferenceEngine& operator=(LocalInferenceEngine&&) = delete;

    // A failed load leaves the engine unloaded. Paths must be absolute POSIX
    // paths without symlinks, traversal, network mounts, or special files.
    Error load(std::string_view model_path, std::string_view audit_path = {}) noexcept;
    Error unload() noexcept;
    bool loaded() const noexcept;
    void cancel() noexcept;

    // Plain prompt input (apply the model's chat template in the caller).
    // Greedy decoding. Output is bytes, not a null-terminated string; UTF-8 may
    // end mid-codepoint at the token limit. Caller owns input and successful
    // output memory. On every failure, the entire output span is wiped.
    Generation generate(std::string_view prompt, std::uint32_t max_tokens,
                        std::span<char> output) noexcept;

private:
#ifdef OMNI_CORE_TESTING
    friend struct EngineTestAccess;
#endif
    static bool aborted(void* engine) noexcept;
    void clear_request() noexcept;
    Error unload_locked() noexcept;
    Error audit(Error error, std::size_t bytes, std::uint32_t tokens) noexcept;
    Generation generate_locked(std::string_view prompt, std::uint32_t max_tokens,
                               std::span<char> output);

    const Config config_;
    mutable std::mutex mutex_;
    std::atomic<bool> cancelled_{false};
    llama_model* model_ = nullptr;
    llama_context* context_ = nullptr;
    std::int32_t* tokens_ = nullptr;
    char* piece_ = nullptr;
    std::size_t piece_capacity_ = 0;
    int audit_fd_ = -1;
};

} // namespace omniagent
